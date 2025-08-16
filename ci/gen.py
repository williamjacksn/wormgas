import json
import pathlib

THIS_FILE = pathlib.PurePosixPath(
    pathlib.Path(__file__).relative_to(pathlib.Path().resolve())
)
ACTIONS_CHECKOUT = {"name": "Check out repository", "uses": "actions/checkout@v5"}


def gen(content: dict, target: str):
    pathlib.Path(target).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(target).write_text(
        json.dumps(content, indent=2, sort_keys=True), newline="\n"
    )


def gen_dependabot():
    target = ".github/dependabot.yaml"
    content = {
        "version": 2,
        "updates": [
            {
                "package-ecosystem": e,
                "allow": [{"dependency-type": "all"}],
                "directory": "/",
                "schedule": {"interval": "daily"},
            }
            for e in ["github-actions", "uv"]
        ],
    }
    gen(content, target)


def gen_deploy_workflow():
    target = ".github/workflows/deploy.yaml"
    content = {
        "env": {
            "description": f"This workflow ({target}) was generated from {THIS_FILE}"
        },
        "name": "Deploy",
        "on": {"push": {"branches": ["master"]}},
        "jobs": {
            "deploy": {
                "name": "Deploy",
                "runs-on": "ubuntu-latest",
                "steps": [
                    ACTIONS_CHECKOUT,
                    {
                        "name": "Deploy",
                        "run": "sh ci/ssh-deploy.sh",
                        "env": {
                            "SSH_HOST": "${{ secrets.ssh_host }}",
                            "SSH_PRIVATE_KEY": "${{ secrets.ssh_private_key }}",
                            "SSH_USER": "${{ secrets.ssh_user }}",
                        },
                    },
                ],
            }
        },
    }
    gen(content, target)


def gen_ruff_workflow():
    target = ".github/workflows/ruff.yaml"
    content = {
        "env": {
            "description": f"This workflow ({target}) was generated from {THIS_FILE}"
        },
        "name": "Ruff",
        "on": {
            "pull_request": {"branches": ["master"]},
            "push": {"branches": ["master"]},
        },
        "permissions": {"contents": "read"},
        "jobs": {
            "ruff": {
                "name": "Run ruff linting and formatting checks",
                "runs-on": "ubuntu-latest",
                "steps": [
                    ACTIONS_CHECKOUT,
                    {
                        "name": "Run ruff check",
                        "uses": "astral-sh/ruff-action@v3",
                        "with": {"args": "check --output-format=github"},
                    },
                    {
                        "name": "Run ruff format",
                        "uses": "astral-sh/ruff-action@v3",
                        "with": {"args": "format --check"},
                    },
                ],
            }
        },
    }
    gen(content, target)


def main():
    gen_dependabot()
    gen_deploy_workflow()
    gen_ruff_workflow()


if __name__ == "__main__":
    main()
