"""Read-only privacy audit of tracked files, commit identities and historical blobs."""

import re
import subprocess

EXPECTED_EMAIL = "156163069+manthan3502@users.noreply.github.com"
# Split token patterns so the scanner's own source is not a false positive.
PRIVATE = re.compile(
    r"[\w.+-]+@(?:gmail|yahoo|hotmail|outlook)\.com"
    r"|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE" + r" KEY-----"
    r"|gh[pousr]_" + r"[A-Za-z0-9]{30,}"
    r"|github_pat_" + r"[A-Za-z0-9_]{30,}"
    r"|AKIA" + r"[A-Z0-9]{16}"
    r"|C:[\\/]Users[\\/]" + r"|D:[\\/]Projects[\\/]"
)


def git(*args):
    return subprocess.check_output(["git", *args])


def run():
    identities = git("log", "--format=%ae%n%ce").decode().splitlines()
    assert identities and all(email == EXPECTED_EMAIL for email in identities), (
        "Unexpected public commit email"
    )
    paths = git("ls-files", "-z").decode().split("\x00")[:-1]
    for path in paths:
        assert path == ".env.example" or not path.startswith(".env"), (
            "Tracked private env file"
        )
        assert not path.endswith((".pem", ".key", ".dump", ".sql.gz")), (
            "Tracked private artifact"
        )
        data = git("show", ":" + path).decode("utf-8", errors="replace")
        assert not PRIVATE.search(data), "Private content detected in tracked files"
    objects = git("rev-list", "--objects", "--all").decode().splitlines()
    blobs = 0
    for entry in objects:
        identity, _, historical_path = entry.partition(" ")
        if historical_path:
            filename = historical_path.rsplit("/", 1)[-1]
            assert filename == ".env.example" or not filename.startswith(".env"), (
                "Historical private env file"
            )
            assert not filename.endswith((".pem", ".key", ".dump", ".sql.gz")), (
                "Historical private artifact"
            )
        if git("cat-file", "-t", identity).strip() != b"blob":
            continue
        data = git("cat-file", "blob", identity).decode("utf-8", errors="replace")
        assert not PRIVATE.search(data), "Private content detected in historical blob"
        blobs += 1
    print(
        f"Repository privacy PASS: {len(paths)} tracked files, {blobs} historical blobs"
    )
    print(
        f"All {len(identities) // 2} commit author/committer identities use the approved noreply"
    )


if __name__ == "__main__":
    run()
