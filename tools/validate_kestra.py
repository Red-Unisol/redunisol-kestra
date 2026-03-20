from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_DIRS = [
    ROOT / 'platform' / 'infra',
    ROOT / 'platform' / 'system' / 'flows',
    ROOT / 'automations',
    ROOT / '.github' / 'workflows',
]


def main() -> int:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED_DIRS if not path.exists()]
    if missing:
        print('Missing required directories:')
        for item in missing:
            print(f'- {item}')
        return 1

    print('Repository structure is valid.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
