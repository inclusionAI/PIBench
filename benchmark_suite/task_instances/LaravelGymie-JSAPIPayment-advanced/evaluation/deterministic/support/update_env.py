"""Set KEY=VALUE pairs in a dotenv file (replace existing line or append)."""
import re
import sys


def main():
    env_path = sys.argv[1]
    pairs = [arg.split("=", 1) for arg in sys.argv[2:]]
    try:
        with open(env_path) as f:
            content = f.read()
    except OSError:
        content = ""
    for key, value in pairs:
        if re.search(r'[\s#"\']', value):
            value = '"%s"' % value.replace("\\", "\\\\").replace('"', '\\"')
        line = "%s=%s" % (key, value)
        pattern = re.compile(r"^%s=.*$" % re.escape(key), re.M)
        if pattern.search(content):
            content = pattern.sub(line.replace("\\", "\\\\"), content)
        else:
            if content and not content.endswith("\n"):
                content += "\n"
            content += line + "\n"
    with open(env_path, "w") as f:
        f.write(content)


if __name__ == "__main__":
    main()
