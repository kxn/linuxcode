#!/usr/bin/ruby
# A scoped codesign command adapter. Real signing uses pinned zsign; verification
# checks the bytes actually sealed. Unsupported certificate/nested-code modes fail.
require 'digest/sha1'
require 'digest/sha2'
require 'cfpropertylist'
require 'pathname'

module LinuxcodeSigning
  def self.check(value, message)
    raise ArgumentError, message unless value
  end
  def self.slice(bytes, offset, length)
    check(offset >= 0 && length >= 0 && offset + length <= bytes.bytesize, 'truncated signature data')
    bytes.byteslice(offset, length)
  end
  def self.u32(bytes, offset, big = false)
    slice(bytes, offset, 4).unpack1(big ? 'N' : 'V')
  end
  def self.plist(bytes)
    CFPropertyList.native_types(CFPropertyList::List.new(:data => bytes).value)
  end
  def self.digest(algorithm, bytes)
    algorithm == 1 ? Digest::SHA1.digest(bytes) : Digest::SHA256.digest(bytes)
  end
  def self.der(bytes)
    cursor = 0
    read_node = lambda do |depth|
      check(depth < 64, 'DER nesting exceeds supported bounds')
      tag = slice(bytes, cursor, 1).unpack1('C'); cursor += 1
      length = slice(bytes, cursor, 1).unpack1('C'); cursor += 1
      if length >= 128
        count = length & 127
        check(count > 0 && count <= 4, 'unsupported DER length')
        raw = slice(bytes, cursor, count); cursor += count
        check(raw.getbyte(0) != 0, 'nonminimal DER length')
        length = raw.bytes.inject(0) { |v, b| (v << 8) | b }
        check(length >= 128, 'nonminimal long DER length')
      end
      finish = cursor + length; check(finish <= bytes.bytesize, 'DER value exceeds blob')
      case tag
      when 1
        raw = slice(bytes, cursor, length); check(length == 1 && [0, 255].include?(raw.getbyte(0)), 'invalid DER boolean')
        cursor = finish; value = raw.getbyte(0) != 0
      when 2
        raw = slice(bytes, cursor, length); check(length > 0 && length <= 8, 'unsupported DER integer')
        check(raw.getbyte(0) < 128 && !(length > 1 && raw.getbyte(0) == 0 && raw.getbyte(1) < 128), 'unsupported/nonminimal DER integer')
        cursor = finish; value = raw.bytes.inject(0) { |v, b| (v << 8) | b }
      when 12
        value = slice(bytes, cursor, length).dup.force_encoding('UTF-8'); check(value.valid_encoding?, 'invalid DER string'); cursor = finish
      when 0x30, 0xb0, 0x70
        children = []; children << read_node.call(depth + 1) while cursor < finish
        check(cursor == finish, 'DER child crosses parent')
        value = children
        if tag == 0xb0
          value = {}
          children.each do |entry|
            check(entry.is_a?(Array) && entry.size == 2 && entry[0].is_a?(String) && !value.key?(entry[0]), 'invalid/duplicate DER dictionary entry')
            value[entry[0]] = entry[1]
          end
        elsif tag == 0x70
          check(children.size == 2 && children[0] == 1 && children[1].is_a?(Hash), 'unsupported DER entitlement version')
          value = children[1]
        end
      else
        raise ArgumentError, "unsupported DER tag #{tag}"
      end
      value
    end
    result = read_node.call(0); check(cursor == bytes.bytesize, 'trailing DER data'); result
  end
  def self.verify(app, expected_entitlements = nil, require_der = false)
    check(File.directory?(app), 'only bundle signing is currently supported')
    info_data = File.binread(File.join(app, 'Info.plist')); info = plist(info_data)
    executable = info.fetch('CFBundleExecutable'); check(!executable.include?('/') && executable != '..', 'invalid executable name')
    binary = File.binread(File.join(app, executable)); check(u32(binary, 0) == 0xfeedfacf, 'only thin 64-bit Mach-O is supported')
    cursor = 32; signature = nil; signature_offset = nil
    u32(binary, 16).times do
      command = u32(binary, cursor); length = u32(binary, cursor + 4)
      check(length >= 8, 'invalid Mach-O command'); slice(binary, cursor, length)
      if command == 0x1d
        check(signature.nil? && length >= 16, 'duplicate/invalid signature command')
        signature_offset = u32(binary, cursor + 8); signature = slice(binary, signature_offset, u32(binary, cursor + 12))
      end
      cursor += length
    end
    check(!signature.nil?, 'missing code signature')
    check(u32(signature, 0, true) == 0xfade0cc0, 'invalid signature superblob')
    limit = u32(signature, 4, true); count = u32(signature, 8, true)
    check(limit <= signature.bytesize && 12 + count * 8 <= limit, 'invalid superblob size')
    blobs = {}; ranges = []
    count.times do |i|
      kind = u32(signature, 12 + i * 8, true); offset = u32(signature, 16 + i * 8, true)
      length = u32(signature, offset + 4, true)
      check(!blobs.key?(kind) && offset >= 12 + count * 8 && length >= 8 && offset + length <= limit, 'invalid superblob entry')
      check(ranges.none? { |a, b| offset < b && a < offset + length }, 'overlapping signature blobs')
      ranges << [offset, offset + length]; blobs[kind] = slice(signature, offset, length)
    end
    cd = blobs.fetch(0); fields = slice(cd, 0, 36).unpack('N9')
    magic, length, version, flags, hash_offset, identifier, special, pages, code_limit = fields
    hash_size, algorithm, _, page_exp = slice(cd, 36, 4).unpack('C4')
    check(magic == 0xfade0c02 && length == cd.bytesize && version <= 0x20600 && flags & 2 != 0, 'unsupported CodeDirectory')
    check([1, 2].include?(algorithm) && hash_size == (algorithm == 1 ? 20 : 32), 'unsupported hash algorithm')
    check([12, 14].include?(page_exp) && code_limit == signature_offset, 'unsupported code-page layout')
    check(special >= 3 && special <= 16 && hash_offset >= special * hash_size && hash_offset + pages * hash_size <= cd.bytesize, 'invalid code hash table')
    page_size = 1 << page_exp
    check(pages == (code_limit + page_size - 1) / page_size, 'incorrect code-page count')
    pages.times do |i|
      actual = digest(algorithm, slice(binary, i * page_size, [page_size, code_limit - i * page_size].min))
      check(actual == slice(cd, hash_offset + i * hash_size, hash_size), 'code page hash mismatch')
    end
    identifier_end = cd.index("\0", identifier); check(identifier_end && identifier < hash_offset, 'invalid code identifier')
    check(slice(cd, identifier, identifier_end - identifier).force_encoding('UTF-8') == info.fetch('CFBundleIdentifier'), 'code identifier mismatch')
    resource_data = File.binread(File.join(app, '_CodeSignature', 'CodeResources'))
    (1..special).each do |slot|
      stored = slice(cd, hash_offset - slot * hash_size, hash_size)
      if stored == "\0" * hash_size
        check(![1, 3].include?(slot), 'missing Info.plist/resource seal'); next
      end
      data = slot == 1 ? info_data : slot == 3 ? resource_data : blobs[slot]
      check([1, 2, 3, 5, 7].include?(slot) && data, 'unsupported special slot')
      check(digest(algorithm, data) == stored, "special slot hash mismatch: #{slot}")
    end
    check(!blobs.key?(0x10000) || blobs[0x10000].bytesize == 8, 'CMS/certificate verification is not implemented')
    if expected_entitlements
      xml = blobs.fetch(5); check(u32(xml, 0, true) == 0xfade7171, 'invalid XML entitlements')
      check(plist(slice(xml, 8, xml.bytesize - 8)) == expected_entitlements, 'XML entitlements mismatch')
    end
    if (require_der && (expected_entitlements || blobs.key?(5))) || blobs.key?(7)
      xml = blobs.fetch(5); encoded = blobs.fetch(7)
      check(u32(encoded, 0, true) == 0xfade7172, 'invalid DER entitlements')
      check(der(slice(encoded, 8, encoded.bytesize - 8)) == plist(slice(xml, 8, xml.bytesize - 8)), 'DER/XML entitlements mismatch')
    end
    resources = plist(resource_data)
    ['files', 'files2'].each do |table|
      resources.fetch(table, {}).each do |name, seal|
        check(!Pathname.new(name).absolute? && !name.split('/').include?('..'), 'invalid sealed path')
        file = File.join(app, name); check(File.file?(file) && !File.symlink?(file), 'missing or unsupported sealed resource')
        bytes = File.binread(file)
        if seal.is_a?(String)
          check(Digest::SHA1.digest(bytes) == seal, 'resource SHA1 mismatch')
        else
          check((seal.keys - ['hash', 'hash2', 'optional']).empty? && (seal['hash'] || seal['hash2']), 'nested/symlink resource seals are not implemented')
          check(!seal['hash'] || Digest::SHA1.digest(bytes) == seal['hash'], 'resource SHA1 mismatch')
          check(!seal['hash2'] || Digest::SHA256.digest(bytes) == seal['hash2'], 'resource SHA256 mismatch')
        end
      end
    end
    Dir.glob(File.join(app, '**', '*'), File::FNM_DOTMATCH).each do |path|
      next if ['.', '..'].include?(File.basename(path))
      check(!File.symlink?(path), 'symlink resource verification is not implemented')
      next unless File.file?(path)
      name = path[(app.size + 1)..-1]; next if name == executable || name.start_with?('_CodeSignature/')
      applicable = resources.fetch('rules2').select { |pattern, _| Regexp.new(pattern).match?(name) }
      check(!applicable.empty?, 'resource has no sealing rule')
      _, rule = applicable.max_by { |_, value| value.is_a?(Hash) ? value.fetch('weight', 1) : 1 }
      omitted = rule.is_a?(Hash) && rule['omit']
      check(omitted || resources.fetch('files2', {}).key?(name), 'unsealed added resource')
    end
    { 'code_pages' => pages, 'special_slots' => special, 'bundle_identifier' => info.fetch('CFBundleIdentifier') }
  end
  def self.linux_path(path)
    path = File.realpath(path); prefix = '/Volumes/SystemRoot/workspace/'
    check(path.start_with?(prefix), 'signing inputs must be inside the selected workspace')
    '/workspace/' + path[prefix.size..-1]
  end
  def self.entitlements_supported(value)
    case value
    when CFPropertyList::CFDictionary then value.value.all? { |key, child| key.is_a?(String) && entitlements_supported(child) }
    when CFPropertyList::CFArray then value.value.all? { |child| entitlements_supported(child) }
    when CFPropertyList::CFString, CFPropertyList::CFBoolean then true
    else false
    end
  end
  def self.main(args)
    force = false; identity = nil; verify_requested = false; short_verify = false; entitlements = nil; generate_der = false; targets = []
    until args.empty?
      arg = args.shift
      case arg
      when '--force', '-f' then force = true
      when '--sign', '-s' then identity = args.shift; check(identity, 'missing signing identity')
      when '--verify' then verify_requested = true
      when '-v', '-vv', '-vvv' then short_verify = true
      when '--strict', '--verbose' then nil
      when /\A--verbose=[0-9]+\z/ then nil
      when '--timestamp=none' then nil
      when '--generate-entitlement-der' then generate_der = true
      when '--entitlements' then entitlements = args.shift; check(entitlements, 'missing entitlements path')
      when '--' then targets.concat(args); args.clear
      else
        check(!arg.start_with?('-'), "unsupported codesign option: #{arg}"); targets << arg
      end
    end
    check(targets.size == 1, 'exactly one bundle is currently supported')
    verify_requested ||= short_verify && identity.nil?
    check((!identity.nil?) != verify_requested, 'choose signing or verification')
    app = File.realpath(targets[0]); check(File.directory?(app), 'only flat bundles are currently supported')
    check(Dir.glob(File.join(app, '**', '*')).none? { |p| File.directory?(p) && p =~ /\.(framework|appex|app)\z/ }, 'nested code signing is not implemented')
    tree = entitlements ? CFPropertyList::List.new(:data => File.binread(entitlements)).value : nil
    expected = tree ? CFPropertyList.native_types(tree) : nil
    check(!tree || (tree.is_a?(CFPropertyList::CFDictionary) && entitlements_supported(tree)), 'unsupported entitlement value; refusing to lose data')
    if identity
      check(identity == '-', 'certificate identity lookup is not implemented')
      check(force || !File.exist?(File.join(app, '_CodeSignature', 'CodeResources')), 'bundle is already signed; use --force')
      command = [ENV.fetch('LINUXCODE_ZSIGN_ELF'), '-a']; command << '-f' if force
      command += ['-e', linux_path(entitlements)] if entitlements
      command << linux_path(app)
      check(system(*command), 'zsign signing failed')
    end
    result = verify(app, expected, generate_der)
    warn "#{targets[0]}: #{identity ? 'signed' : 'verified'} ad-hoc (#{result['code_pages']} code pages)"
    0
  rescue StandardError => error
    warn "codesign: #{error.message}"
    1
  end
end
exit LinuxcodeSigning.main(ARGV) if $PROGRAM_NAME == __FILE__
