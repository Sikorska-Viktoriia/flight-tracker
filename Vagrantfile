require_relative "vagrant/nodes"

Vagrant.configure("2") do |config|
  config.vm.box = "bento/ubuntu-24.04"
  config.vm.synced_folder ".", "/vagrant", disabled: true

  FlightTrackerVagrant.configure(config)
end
