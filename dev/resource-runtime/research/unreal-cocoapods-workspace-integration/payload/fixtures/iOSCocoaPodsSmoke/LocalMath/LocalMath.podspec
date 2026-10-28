Pod::Spec.new do |spec|
  spec.name = 'LocalMath'
  spec.version = '0.1.0'
  spec.summary = 'Local dependency for Linux Darling integration checks.'
  spec.homepage = 'https://example.invalid/LocalMath'
  spec.license = { :type => 'MIT', :text => 'Copyright 2026. Permission is granted to use, copy, modify and distribute this test fixture without warranty.' }
  spec.author = 'Linuxcode'
  spec.source = { :git => 'https://example.invalid/LocalMath.git', :tag => spec.version.to_s }
  spec.ios.deployment_target = '15.0'
  spec.source_files = '*.{c,h}'
end
