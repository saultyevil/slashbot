import logging


def setup_response_logger(model_name: str) -> logging.Logger:
    """Set up a debug logger for logging responses and requests.

    Parameters
    ----------
    model_name : str
        The name of the model.

    Returns
    -------
    logging.Logger
        The initialised logger.

    """
    handler = logging.FileHandler(f"logs/{model_name}-requests.log", mode="w")
    formatter = logging.Formatter("%(asctime)s | %(message)s")
    handler.setFormatter(formatter)

    logger = logging.getLogger(f"TextGenerationAbstractClient-{model_name}")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    return logger
