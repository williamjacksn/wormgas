#!/bin/sh

if [[ "`whoami`" != "root" ]]
then
	echo -e "Must be root to install. If you don't want to run this script as root, install the following packages by hand :\n\t- Python lxml\n"
	exit
fi

pip=`whereis pip | cut -d\: -f2`

if [[ "$pip" == "" ]]
then
	pip=`whereis pip2 | cut -d\: -f2`
fi

if [[ "$pip" == "" ]]
then
	echo "Python Pip not found. Please check if it is installed."
fi

exec $pip install lxml
