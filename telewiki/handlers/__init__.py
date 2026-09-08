"""Bot handler registration."""


def register_all(app) -> None:
    from telewiki.handlers import digest, quiz, start, wiki

    start.register(app)
    wiki.register(app)
    quiz.register(app)
    digest.register(app)
