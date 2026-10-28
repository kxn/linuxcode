#!/usr/bin/env ruby
# Host Linux Ruby check of original xcodeproj APIs on disposable project copies.
# This does not run CocoaPods CLI, Darling, native compilers, UBT, or Xcode.
require 'pathname'
require 'tmpdir'
require 'fileutils'
require 'json'
require 'digest'
repo = Pathname.new(__dir__).parent
Dir[(repo + 'runtime/state/prefix/Library/Ruby/Gems/2.6.0/gems/*/lib').to_s].each { |path| $LOAD_PATH.unshift(path) }
require_relative 'inspect-unreal-pods-project'

class HookOnlyPodfile
  attr_reader :install_hook, :integrate_hook
  def platform(*); end
  def source(*); end
  def project(*); end
  def workspace(*); end
  def pod(*); end
  def target(*)
    yield
  end
  def post_install(&hook)
    @install_hook = hook
  end
  def post_integrate(&hook)
    @integrate_hook = hook
  end
end

project = Pathname.new(ARGV.fetch(0)).realpath
name = ARGV.fetch(1, 'LinuxcodeUESmoke')
raise 'Unexpected target name' unless /\A[A-Za-z][A-Za-z0-9_]*\z/.match?(name)
xcode_project = LinuxcodeUnrealPods.project_path(project, name)
relative_project = xcode_project.relative_path_from(project)
original_pbx = xcode_project + 'project.pbxproj'
original_workspace = project + "#{name} (IOS).xcworkspace/contents.xcworkspacedata"
original_digests = [original_pbx, original_workspace].map { |path| [path, Digest::SHA256.file(path).hexdigest] }.to_h
folder = Pathname.new(Dir.mktmpdir('unreal-pods-hook-check-', (repo + 'runtime').to_s))
fixture = folder + 'fixture'
FileUtils.mkdir_p((fixture + relative_project).parent)
FileUtils.cp_r(xcode_project, fixture + relative_project)
FileUtils.cp_r(xcode_project.parent + 'XcconfigsIOS', (fixture + relative_project).parent + 'XcconfigsIOS')
FileUtils.cp_r(original_workspace.dirname, fixture + original_workspace.dirname.basename)
FileUtils.cp_r(project + 'Pods', fixture + 'Pods')
%w(unreal-pods-before.json unreal-pods-preparation.json).each do |file|
  FileUtils.cp(project + file, fixture + file) if (project + file).file?
end
template = (repo + 'fixtures/UECocoaPodsSmoke/Podfile.template').read.gsub('@TARGET@', name).gsub('@PROJECT@', relative_project.to_s).gsub('@INSPECTOR@', (repo + 'scripts/inspect-unreal-pods-project.rb').to_s)
(fixture + 'Podfile').write(template)
dsl = HookOnlyPodfile.new
dsl.instance_eval(template, (fixture + 'Podfile').to_s)
before = JSON.parse((fixture + 'unreal-pods-before.json').read)
pods = Xcodeproj::Project.open(fixture + 'Pods/Pods.xcodeproj')
installer = Struct.new(:sandbox, :pods_project).new(Struct.new(:root).new(fixture + 'Pods'), pods)
dsl.install_hook.call(installer)
pods.save
# The real CocoaPods UserProjectIntegrator uses this original workspace API.
workspace = Xcodeproj::Workspace.new_from_xcworkspace(fixture + "#{name} (IOS).xcworkspace")
[relative_project.to_s, 'Pods/Pods.xcodeproj'].each do |path|
  workspace << Xcodeproj::Workspace::FileReference.new(path, 'group')
end
workspace.save_as(fixture + "#{name} (IOS).xcworkspace")
dsl.integrate_hook.call(installer)
report = JSON.parse((fixture + 'unreal-pods-integration.json').read)
raise 'Expected original xcodeproj to normalize both UE schema extensions' unless report['native_xcodeproj_normalized_input_attributes'].size == 2
raise 'Missing app xcconfig wrappers' unless report['app_xcconfig_wrappers'].size == 5
baseline_sha = Digest::SHA256.file(fixture + 'unreal-pods-before.json').hexdigest

# A second hook invocation must reuse the original dependency rather than duplicate it.
dsl.integrate_hook.call(installer)
reloaded = HookOnlyPodfile.new
reloaded.instance_eval(template, (fixture + 'Podfile').to_s)
reloaded.integrate_hook.call(installer)
raise 'First original baseline was overwritten' unless Digest::SHA256.file(fixture + 'unreal-pods-before.json').hexdigest == baseline_sha
user = Xcodeproj::Project.open(fixture + relative_project)
legacy = user.targets.find { |target| target.name == "#{name}_Build" }
raise 'Duplicate cross-project dependencies' unless legacy.dependencies.size == 1

# Corrupt a copy's original command and ensure the inspector rejects it.
legacy.build_arguments_string += ' changed'
user.save
command_change_rejected = false
begin
  LinuxcodeUnrealPods.verify(fixture, name, before)
rescue RuntimeError => error
  raise unless error.message.include?('build_arguments changed')
  command_change_rejected = true
end
raise 'Command corruption was not detected' unless command_change_rejected

# A target with no original base must import the matching project-level base.
legacy.build_arguments_string = before['targets'].find { |target| target['name'] == "#{name}_Build" }['build_arguments']
app = user.native_targets.find { |target| target.name == name }
debug = app.build_configurations.find { |config| config.name == 'Debug' }
original_debug = before['targets'].find { |target| target['name'] == name }['configurations'].find { |config| config['name'] == 'Debug' }
project_debug = user.build_configurations.find { |config| config.name == 'Debug' }
project_debug.base_configuration_reference = user.objects_by_uuid[original_debug['base_uuid']]
debug.base_configuration_reference = nil
user.save
fallback_before = LinuxcodeUnrealPods.snapshot(fixture, name)
# Restore the other app configurations' original references in this test baseline.
fallback_before['targets'].find { |target| target['name'] == name }['configurations'].each do |config|
  next if config['name'] == 'Debug'
  config.replace(before['targets'].find { |target| target['name'] == name }['configurations'].find { |row| row['name'] == config['name'] })
end
LinuxcodeUnrealPods.integrate_xcconfigs(fixture, name, user, fallback_before)
user.save
fallback_report = LinuxcodeUnrealPods.verify(fixture, name, fallback_before)
raise 'Project-level configuration fallback failed' unless fallback_report['app_xcconfig_wrappers'].find { |config| config['configuration'] == 'Debug' }['original_UE_xcconfig'].end_with?("#{name}_Debug.xcconfig")
raise 'Live original changed during check' unless original_digests.all? { |path, digest| Digest::SHA256.file(path).hexdigest == digest }
result = {
  'verified' => true, 'original_xcodeproj_version' => Xcodeproj::VERSION,
  'host_Ruby_version' => RUBY_VERSION,
  'scope' => 'Original xcodeproj metadata APIs and Podfile hooks on disposable copies; no CocoaPods CLI or native build',
  'cross_project_dependency_and_shared_archive_directory_verified' => true,
  'repeated_hook_did_not_duplicate_dependency' => true,
  'original_command_corruption_rejected' => command_change_rejected,
  'app_imports_UE_and_real_CocoaPods_settings' => true,
  'original_baseline_preserved_across_Podfile_reload' => true,
  'target_without_base_inherits_same_named_project_configuration' => true,
  'app_shared_archive_directory_uses_selected_configuration_despite_UE_CONFIGURATION_clear' => true,
  'original_project_files_unchanged' => true, 'native_process_started' => false,
  'pod_install_verified' => false, 'pod_compile_verified' => false, 'full_app_build_verified' => false,
  'integration' => report,
  'files' => [Pathname.new(__FILE__).realpath, repo + 'scripts/inspect-unreal-pods-project.rb',
              repo + 'fixtures/UECocoaPodsSmoke/Podfile.template'].map do |path|
    [path.relative_path_from(repo).to_s, Digest::SHA256.file(path).hexdigest]
  end.to_h
}
(folder + 'result.json').write(JSON.pretty_generate(result) + "\n")
puts "EVIDENCE #{folder + 'result.json'}"
