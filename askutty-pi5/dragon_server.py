"""WSGI entry point for the Universal Dragon NOVA Core sidecar."""

from dotenv import load_dotenv

from universal_dragon import DragonConfig, create_app


load_dotenv()
config = DragonConfig.from_env()
app = create_app(config)


if __name__ == "__main__":
    app.run(host=config.bind_host, port=config.port, debug=False)

