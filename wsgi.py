from archiver import foreman

app = foreman.build_app()

foreman.config_logging(app, None)

if __name__ == '__main__':
    foreman.start(app)
