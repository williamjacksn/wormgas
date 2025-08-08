install --mode=600 -D /dev/null ~/.ssh/id_ed25519
echo "${SSH_PRIVATE_KEY}" > ~/.ssh/id_ed25519
ssh-keyscan -H -p 2234 "${SSH_HOST}" > ~/.ssh/known_hosts
ssh ssh://${SSH_USER}@${SSH_HOST}:2234 git -C /home/rainwave/wormgas pull --ff-only
ssh ssh://${SSH_USER}@${SSH_HOST}:2234 sudo systemctl restart wormgas.service
