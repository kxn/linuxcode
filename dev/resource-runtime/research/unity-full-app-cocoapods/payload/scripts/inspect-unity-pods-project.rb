require 'xcodeproj'
require 'digest'
require 'json'

project = Xcodeproj::Project.open(ARGV.fetch(0))
targets = project.targets.map do |target|
  {
    'name' => target.name,
    'uuid' => target.uuid,
    'product_type' => target.product_type,
    'sources' => target.source_build_phase.files_references.map(&:path).sort,
    'shell_phases' => target.shell_script_build_phases.map do |phase|
      {'uuid' => phase.uuid, 'name' => phase.name,
       'script_sha256' => Digest::SHA256.hexdigest(phase.shell_script || '')}
    end,
    'configurations' => target.build_configurations.map do |config|
      {'name' => config.name, 'base_configuration' => config.base_configuration_reference&.path,
       'settings' => config.build_settings}
    end
  }
end
File.write(ARGV.fetch(1), JSON.pretty_generate({'targets' => targets}) + "\n")
