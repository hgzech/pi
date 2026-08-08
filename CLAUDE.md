# pi

Static site (GitHub Pages) served from `main` at https://github.com/hgzech/pi.
Main page is `index.html`; peg pages live in `pegs/`.

## Git

Push access is configured via an SSH deploy key stored at `.git/pi_deploy_key`
(inside `.git`, so it is never committed). Repo-local config already set:

- `origin` = `git@github.com:hgzech/pi.git`
- `core.sshCommand` = `ssh -i .git/pi_deploy_key -o UserKnownHostsFile=.git/known_hosts -o IdentitiesOnly=yes`

So `git push` just works — no extra flags needed.

Hilmar's preference: for small changes, commit and push automatically rather
than asking first.
