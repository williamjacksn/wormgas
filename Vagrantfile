# -*- mode: ruby -*-
# vi: set ft=ruby :

provision_script = <<END_OF_LINE

aptitude update
aptitude --assume-yes full-upgrade
aptitude --assume-yes install htop python3-pip
apt-get autoremove
aptitude clean

pip3 install --upgrade pep8

END_OF_LINE

VAGRANTFILE_API_VERSION = "2"

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
    config.vm.box = "ubuntu/trusty64"
    # config.vm.box_check_update = false
    config.vm.provision :shell, :inline => provision_script
end
