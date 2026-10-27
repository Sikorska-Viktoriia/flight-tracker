from urllib.request import urlopen


def main() -> None:
    with urlopen("http://127.0.0.1:8000/health/ready", timeout=2) as response:
        if response.status >= 400:
            raise SystemExit(f"health check returned HTTP {response.status}")


if __name__ == "__main__":
    main()
