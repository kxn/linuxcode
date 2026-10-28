# Read-only project inspection shared by the Podfile hook and command line.
# Uses the original xcodeproj APIs; it does not patch their parser or writer.
require 'xcodeproj'
require 'json'
require 'digest'
require 'rexml/document'
require 'fileutils'

module LinuxcodeUnrealPods
  def self.check(condition, message)
    raise message unless condition
  end

  def self.project_path(root, name)
    root = Pathname.new(root).expand_path
    workspace = Xcodeproj::Workspace.new_from_xcworkspace(root + "#{name} (IOS).xcworkspace")
    matches = workspace.file_references.select { |ref| File.basename(ref.path) == "#{name} (IOS).xcodeproj" }
    check(matches.size == 1, 'Original workspace must identify exactly one UE game project')
    path = Pathname.new(matches.first.absolute_path(root)).cleanpath
    check(!path.relative_path_from(root).each_filename.include?('..'), 'UE project escapes fixture root')
    check((path + 'project.pbxproj').file?, 'Workspace UE game project does not exist')
    path
  end

  def self.snapshot(root, name)
    root = Pathname.new(root).expand_path
    path = project_path(root, name)
    project = Xcodeproj::Project.open(path)
    raw = Xcodeproj::Plist.read_from_path(path + 'project.pbxproj')
    workspace = root + "#{name} (IOS).xcworkspace/contents.xcworkspacedata"
    xml = REXML::Document.new(workspace.read)
    targets = project.targets.map do |target|
      known = target.attributes.map(&:plist_name) + ['isa']
      {
        'uuid' => target.uuid, 'name' => target.name, 'isa' => target.isa,
        'product_type' => target.respond_to?(:product_type) ? target.product_type : nil,
        # UE writes some fields absent from xcodeproj's schema. Original
        # xcodeproj warns and drops them on save; record this without a shim.
        'unsupported_input_attributes' => raw.fetch('objects').fetch(target.uuid).reject { |key, _| known.include?(key) },
        'dependencies' => target.dependencies.map { |dep| dep.target && dep.target.uuid }.compact,
        'sources' => target.build_phases.select { |phase| phase.isa == 'PBXSourcesBuildPhase' }
                          .flat_map { |phase| phase.files_references.map(&:path) }.sort,
        'shell_phases' => target.shell_script_build_phases.map do |phase|
          {'uuid' => phase.uuid, 'name' => phase.name,
           'script_sha256' => Digest::SHA256.hexdigest(phase.shell_script || '')}
        end,
        'configurations' => target.build_configurations.map do |config|
          base = config.base_configuration_reference
          {'name' => config.name, 'base_uuid' => base && base.uuid,
           'base_sha256' => base && base.real_path.file? ? Digest::SHA256.file(base.real_path).hexdigest : nil}
        end
      }.merge(target.isa == 'PBXLegacyTarget' ? {
        'build_tool' => target.build_tool_path,
        'build_arguments' => target.build_arguments_string,
        'working_directory' => target.build_working_directory,
        'export_build_settings' => target.pass_build_settings_in_environment
      } : {})
    end
    {'targets' => targets, 'xcode_project' => path.relative_path_from(root).to_s,
     'project_configurations' => project.build_configurations.map do |config|
       ref = config.base_configuration_reference
       {'name' => config.name, 'base_uuid' => ref && ref.uuid,
        'base_sha256' => ref && ref.real_path.file? ? Digest::SHA256.file(ref.real_path).hexdigest : nil}
     end,
     'original_UE_xcconfig_files' => Dir[(path.parent + 'XcconfigsIOS/*.xcconfig').to_s].sort.map do |file|
       [Pathname.new(file).relative_path_from(root).to_s, Digest::SHA256.file(file).hexdigest]
     end.to_h,
     'scheme_sha256' => Dir[(path + 'xcshareddata/xcschemes/*.xcscheme').to_s].sort.map do |file|
       [Pathname.new(file).relative_path_from(root).to_s, Digest::SHA256.file(file).hexdigest]
     end.to_h,
     'workspace_references' => xml.get_elements('/Workspace//FileRef').map { |ref| ref.attributes['location'] },
     'pbx_sha256' => Digest::SHA256.file(path + 'project.pbxproj').hexdigest}
  end

  def self.xcconfig_inputs(root, name, project, before, config)
    original = before.fetch('targets').find { |target| target['name'] == name }
    row = original.fetch('configurations').find { |item| item['name'] == config.name }
    check(row, "Original UE configuration missing: #{config.name}")
    unless row['base_uuid']
      row = (before['project_configurations'] || []).find { |item| item['name'] == config.name }
      unless row && row['base_uuid']
        # Compatibility with the first native install's older snapshot format.
        inherited = project.build_configurations.find { |item| item.name == config.name }
        ref = inherited && inherited.base_configuration_reference
        check(ref, "No original target/project UE xcconfig for #{config.name}")
        preparation = JSON.parse((root + 'unreal-pods-preparation.json').read)
        key = File.join(preparation.fetch('project'), ref.real_path.relative_path_from(root))
        input = preparation.fetch('original_inputs').fetch(key)
        row = {'base_uuid' => ref.uuid, 'base_sha256' => input.fetch('sha256')}
      end
    end
    ue = project.objects_by_uuid[row.fetch('base_uuid')]
    check(ue && ue.real_path.file?, "Original UE xcconfig reference missing for #{config.name}")
    check(Digest::SHA256.file(ue.real_path).hexdigest == row.fetch('base_sha256'),
          "Original UE xcconfig bytes changed: #{config.name}")
    pod = root + "Pods/Target Support Files/Pods-#{name}/Pods-#{name}.#{config.name.downcase}.xcconfig"
    check(pod.file?, "Generated CocoaPods xcconfig missing: #{pod}")
    wrapper = root + "Intermediate/LinuxcodePods/Xcconfigs/#{name}-#{config.name}.xcconfig"
    [ue.real_path, pod, wrapper]
  end

  def self.wrapper_content(root, config, ue, pod, wrapper)
    # UE deliberately clears CONFIGURATION in its app xcconfig to retain its
    # output layout. This per-configuration wrapper uses the selected name so
    # it still finds the archive built by the Pods/legacy configuration.
    library = File.join(root, 'Intermediate', 'LinuxcodePods', "#{config.name}-$(PLATFORM_NAME)")
    "// UE and CocoaPods configuration wrapper; original inputs are untouched.\n" \
      "#include \"#{ue.relative_path_from(wrapper.dirname)}\"\n" \
      "#include \"#{pod.relative_path_from(wrapper.dirname)}\"\n" \
      "LINUXCODE_POD_LIBRARY_DIR = #{library}\n" \
      "LIBRARY_SEARCH_PATHS = $(inherited) \"$(LINUXCODE_POD_LIBRARY_DIR)\"\n"
  end

  def self.integrate_xcconfigs(root, name, project, before)
    root = Pathname.new(root).expand_path
    app = project.native_targets.find { |target| target.name == name }
    check(app, 'Original UE app target missing')
    app.build_configurations.each do |config|
      ue, pod, wrapper = xcconfig_inputs(root, name, project, before, config)
      FileUtils.mkdir_p(wrapper.dirname)
      wrapper.write(wrapper_content(root, config, ue, pod, wrapper))
      reference = project.reference_for_path(wrapper) || project.main_group.new_file(wrapper.to_s)
      config.base_configuration_reference = reference
    end
  end

  def self.verify_xcconfigs(root, name, project, before)
    originals = before['original_UE_xcconfig_files']
    unless originals
      preparation = JSON.parse((root + 'unreal-pods-preparation.json').read)
      prefix = preparation.fetch('project') + '/'
      originals = preparation.fetch('original_inputs').each_with_object({}) do |(path, input), result|
        result[path.delete_prefix(prefix)] = input.fetch('sha256') if path.start_with?(prefix) && path.end_with?('.xcconfig')
      end
    end
    check(!originals.empty?, 'Original UE xcconfig evidence is absent')
    originals.each do |path, expected|
      check(Digest::SHA256.file(root + path).hexdigest == expected, "Original UE xcconfig bytes changed: #{path}")
    end
    app = project.native_targets.find { |target| target.name == name }
    app.build_configurations.map do |config|
      ue, pod, wrapper = xcconfig_inputs(root, name, project, before, config)
      reference = config.base_configuration_reference
      check(reference && reference.real_path == wrapper, "App does not use wrapper: #{config.name}")
      check(wrapper.read == wrapper_content(root, config, ue, pod, wrapper), "Wrapper content changed: #{config.name}")
      parsed = Xcodeproj::Config.new(wrapper.to_s)
      check(parsed.includes == [ue.relative_path_from(wrapper.dirname).to_s, pod.relative_path_from(wrapper.dirname).to_s],
            "Wrapper must include UE then Pods: #{config.name}")
      effective = parsed.to_hash
      check(effective['PODS_ROOT'] && effective['OTHER_LDFLAGS'].to_s.include?('LocalMath'),
            "Wrapper does not import CocoaPods build settings: #{config.name}")
      check(effective['LIBRARY_SEARCH_PATHS'].include?('$(LINUXCODE_POD_LIBRARY_DIR)'),
            "Wrapper lacks shared Pod archive search path: #{config.name}")
      {'configuration' => config.name, 'wrapper' => wrapper.relative_path_from(root).to_s,
       'original_UE_xcconfig' => ue.relative_path_from(root).to_s,
       'original_UE_xcconfig_sha256' => Digest::SHA256.file(ue).hexdigest,
       'pods_xcconfig' => pod.relative_path_from(root).to_s,
       'wrapper_sha256' => Digest::SHA256.file(wrapper).hexdigest,
       'PODS_ROOT' => effective['PODS_ROOT'], 'LIBRARY_SEARCH_PATHS' => effective['LIBRARY_SEARCH_PATHS']}
    end
  end

  def self.verify(root, name, before)
    root = Pathname.new(root).expand_path
    after = snapshot(root, name)
    check(after['xcode_project'] == before['xcode_project'], 'Original workspace game project changed')
    check(after['scheme_sha256'] == before['scheme_sha256'], 'Original UE scheme changed')
    before.fetch('targets').each do |original|
      current = after.fetch('targets').find { |target| target['uuid'] == original['uuid'] }
      check(current, "Original target disappeared: #{original['name']}")
      %w(name isa product_type build_tool build_arguments working_directory export_build_settings).each do |key|
        check(current[key] == original[key], "Original #{original['name']} #{key} changed")
      end
      check(current['configurations'].map { |item| item['name'] } == original['configurations'].map { |item| item['name'] },
            "Original configuration names changed: #{original['name']}")
      if original['name'] != name
        check(current['configurations'] == original['configurations'], "Original configurations changed: #{original['name']}")
      end
      check((original['dependencies'] - current['dependencies']).empty?, 'Original UE dependency removed')
      check((original['sources'] - current['sources']).empty?, 'Original source removed')
      check((original['shell_phases'] - current['shell_phases']).empty?, 'Original UE shell phase changed')
    end
    # Compare counts as well as membership, retaining even duplicate original refs.
    before.fetch('workspace_references').uniq.each do |ref|
      check(after['workspace_references'].count(ref) >= before['workspace_references'].count(ref),
            "Original workspace reference removed: #{ref}")
    end
    ['group:Pods/Pods.xcodeproj'].each do |ref|
      check(after['workspace_references'].include?(ref), "Integrated workspace reference missing: #{ref}")
    end
    project = Xcodeproj::Project.open(project_path(root, name))
    legacy = project.targets.find { |target| target.name == "#{name}_Build" }
    app = project.targets.find { |target| target.name == name }
    pods = Xcodeproj::Project.open(root + 'Pods/Pods.xcodeproj')
    pod = pods.targets.find { |target| target.name == 'LocalMath' }
    check(legacy && legacy.isa == 'PBXLegacyTarget', 'Original UE legacy target missing')
    check(app && app.dependencies.any? { |dep| dep.target == legacy }, 'App no longer depends on original UBT target')
    check(pod && pod.product_reference.path == 'libLocalMath.a', 'LocalMath archive target missing')
    check(pod.source_build_phase.files_references.any? { |ref| File.basename(ref.path) == 'LocalMath.c' },
          'Real LocalMath C source is absent from Pods target')
    dependency = legacy.dependency_for_target(pod)
    check(dependency && dependency.target_proxy.remote?, 'UBT target does not depend on LocalMath across projects')
    output = File.join(root, 'Intermediate', 'LinuxcodePods', '$(CONFIGURATION)-$(PLATFORM_NAME)')
    legacy.build_configurations.each do |config|
      check(config.build_settings['LINUXCODE_POD_LIBRARY_DIR'] == output, 'UBT Pod library directory mismatch')
    end
    pod.build_configurations.each do |config|
      check(config.build_settings['CONFIGURATION_BUILD_DIR'] == output, 'Pod output directory mismatch')
    end
    check(legacy.pass_build_settings_in_environment == '1', 'UBT target does not export build settings')
    wrappers = verify_xcconfigs(root, name, project, before)
    {'project_metadata_verified' => true,
     'original_targets_commands_sources_shell_scripts_and_workspace_references_preserved' => true,
     'native_xcodeproj_normalized_input_attributes' => before['targets'].map do |target|
       {'target' => target['name'], 'attributes' => target['unsupported_input_attributes']}
     end.reject { |row| row['attributes'].empty? },
     'legacy_target_uuid' => legacy.uuid, 'pod_target_uuid' => pod.uuid,
     'original_workspace_game_project' => before['xcode_project'],
     'original_UE_schemes_preserved' => true,
     'original_UE_xcconfig_bytes_preserved' => true,
     'app_imports_original_UE_and_CocoaPods_xcconfigs' => true,
     'app_xcconfig_wrappers' => wrappers,
     'cross_project_dependency_uuid' => dependency.uuid,
     'original_build_tool' => legacy.build_tool_path,
     'original_build_arguments' => legacy.build_arguments_string,
     'original_working_directory' => legacy.build_working_directory,
     'original_workspace_references' => before['workspace_references'],
     'workspace_references_after' => after['workspace_references'],
     'pod_archive_directory' => output,
     'ordinary_UE_project_fixture' => true, 'fixture_authored_by_linuxcode' => true,
     'engine_source_modified' => false, 'pod_compile_verified' => false,
     'full_app_build_verified' => false}
  end
end

if $PROGRAM_NAME == __FILE__
  mode, root, name, output, baseline = ARGV
  raise 'Usage: inspect-unreal-pods-project.rb snapshot|verify PROJECT TARGET OUTPUT [BASELINE]' unless output && %w(snapshot verify).include?(mode)
  result = mode == 'snapshot' ? LinuxcodeUnrealPods.snapshot(root, name) :
    LinuxcodeUnrealPods.verify(root, name, JSON.parse(File.read(baseline)))
  File.write(output, JSON.pretty_generate(result) + "\n")
end
