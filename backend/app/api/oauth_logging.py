import logging

CALLBACK = "/api/tool-connections/oauth/callback"


class OAuthAccessFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            args = list(record.args)
            if isinstance(args[2], str) and args[2].split("?", 1)[0] == CALLBACK:
                args[2] = CALLBACK
                record.args = tuple(args)
        return True


def install_oauth_access_filter():
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(value, OAuthAccessFilter) for value in logger.filters):
        logger.addFilter(OAuthAccessFilter())
