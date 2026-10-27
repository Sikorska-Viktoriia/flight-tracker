module FlightTrackerVagrant
  VM_CONFIGS = [
    {
      name: "bastion",
      role: "bastion",
      ip: "10.20.0.2",
      host_ip: "192.168.56.20",
      memory: 384,
      cpus: 1,
      folders: [],
      autostart: true,
    },
    {
      name: "database",
      role: "database",
      ip: "10.20.0.10",
      memory: 768,
      cpus: 1,
      logger_host: true,
      folders: [
        ["database", "/opt/flight-tracker/database"],
        ["history", "/opt/flight-tracker/history"],
      ],
      needs_env: true,
      autostart: true,
    },
    {
      name: "fetcher",
      role: "fetcher",
      ip: "10.20.0.11",
      memory: 384,
      cpus: 1,
      logger_client: true,
      folders: [["fetcher", "/opt/flight-tracker/fetcher"]],
      needs_env: true,
      autostart: true,
    },
    {
      name: "history",
      role: "history",
      ip: "10.20.0.12",
      memory: 768,
      cpus: 1,
      logger_client: true,
      folders: [
        ["database", "/opt/flight-tracker/database"],
        ["history", "/opt/flight-tracker/history"],
      ],
      needs_env: true,
      autostart: true,
    },
    {
      name: "ui",
      role: "ui",
      ip: "10.20.0.13",
      memory: 384,
      cpus: 1,
      logger_client: true,
      folders: [["frontend", "/opt/flight-tracker/frontend"]],
      autostart: true,
      lan_access: true,
    },
  ].freeze

  PROJECT_ROOT = File.expand_path("..", __dir__)
  INTERNAL_NET_NAME = "flight-tracker-internal"

  def self.configure(config)
    ssh_public_key = ENV["VAGRANT_SSH_PUBLIC_KEY"]
    ssh_public_key = File.expand_path(ssh_public_key) if ssh_public_key && !ssh_public_key.empty?

    if ssh_public_key.nil? || ssh_public_key.empty?
      ssh_public_key = %w[id_ed25519.pub id_ecdsa.pub id_rsa.pub]
        .map { |name| File.expand_path("~/.ssh/#{name}") }
        .find { |path| File.file?(path) }
    end

    unless ssh_public_key && File.file?(ssh_public_key)
      raise "Set VAGRANT_SSH_PUBLIC_KEY to a readable SSH public key or place id_ed25519.pub in ~/.ssh/"
    end

    VM_CONFIGS.each do |vm|
      configure_vm(config, vm, File.expand_path(ssh_public_key))
    end
  end

  def self.configure_vm(config, vm, ssh_public_key)
    config.vm.define vm[:name], autostart: vm[:autostart] do |node|
      node.vm.hostname = "flight-tracker-#{vm[:name]}"


      node.vm.network "private_network",
        ip: vm[:ip],
        virtualbox__intnet: INTERNAL_NET_NAME


      if vm[:host_ip]
        node.vm.network "private_network", ip: vm[:host_ip]
        node.vm.provision "file",
          source: ssh_public_key,
          destination: "/tmp/flight-tracker-jump.pub"
      end

      node.vm.provision "file",
        source: ssh_public_key,
        destination: "/tmp/flight-tracker-host.pub"

      %w[scripts compose/vagrant configs logger provision].each do |directory|
        host_dir = File.join(PROJECT_ROOT, directory)
        if File.directory?(host_dir)
          file_mode = directory == "scripts" ? "755" : "644"
          node.vm.synced_folder host_dir,
            "/opt/flight-tracker/#{directory}",
            mount_options: ["dmode=755", "fmode=#{file_mode}"]
        end
      end


      vm[:folders].each do |source, destination|
        host_folder = File.join(PROJECT_ROOT, source)
        if File.directory?(host_folder)
          node.vm.synced_folder host_folder, destination,
            mount_options: ["dmode=755", "fmode=644"]
        end
      end


      if vm[:needs_env]
        env_path = File.join(PROJECT_ROOT, ".env")
        if File.file?(env_path)
          node.vm.provision "file",
            source: env_path,
            destination: "/tmp/flight-tracker.env"
        end
      end


      if vm[:lan_access]
        node.vm.network "forwarded_port",
          guest: 80,
          host: 8080,
          host_ip: "0.0.0.0",
          auto_correct: true,
          id: "ui-http"
      end

      if (vm[:lan_access] || vm[:host_ip]) && ENV["VAGRANT_BRIDGE"]
        node.vm.network "public_network", bridge: ENV["VAGRANT_BRIDGE"]
      end

      node.vm.provider "virtualbox" do |vb|
        vb.name = "flight-tracker-#{vm[:name]}"
        vb.memory = vm[:memory]
        vb.cpus = vm[:cpus]
      end

      node.vm.provision "shell",
        path: File.join(PROJECT_ROOT, "scripts/provision-vm.sh"),
        args: [vm[:role]]

      if vm[:logger_host]
        node.vm.provision "shell",
          path: File.join(PROJECT_ROOT, "scripts/provision-logger.sh")
      elsif vm[:logger_client]
        node.vm.provision "shell",
          path: File.join(PROJECT_ROOT, "scripts/provision-logger-client.sh")
      end
    end
  end
end