# -*- mode: ruby -*-
# vi: set ft=ruby :

one = <<END_OF_LINE

export DEBIAN_FRONTEND=noninteractive
aptitude update
aptitude --assume-yes full-upgrade
aptitude --assume-yes install git libbz2-dev libreadline-dev libsqlite3-dev libssl-dev
apt-get autoremove
aptitude clean

echo '\nKexAlgorithms=diffie-hellman-group1-sha1\n' >> /etc/ssh/sshd_config
/etc/init.d/ssh restart

END_OF_LINE

two = <<END_OF_LINE

curl --location --silent https://raw.githubusercontent.com/yyuu/pyenv-installer/master/bin/pyenv-installer | bash
echo '\nexport PATH="$HOME/.pyenv/bin:$PATH"\neval "$(pyenv init -)"\neval "$(pyenv virtualenv-init -)"\n' >> /home/vagrant/.profile
source /home/vagrant/.profile
/home/vagrant/.pyenv/bin/pyenv install 3.4.3
/home/vagrant/.pyenv/bin/pyenv rehash
/home/vagrant/.pyenv/bin/pyenv global 3.4.3

/home/vagrant/.pyenv/shims/pip install --upgrade pip
/home/vagrant/.pyenv/shims/pip install -r /vagrant/requirements.txt

END_OF_LINE

VAGRANTFILE_API_VERSION = "2"

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
    config.vm.box = "deimosfr/debian-jessie"
    # config.vm.box_check_update = false
    config.vm.provision "one", type: "shell", inline: one
    config.vm.provision "two", type: "shell", privileged: false, inline: two
end
