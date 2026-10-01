class Color:
    # ANSI escape color codes
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[0m"

class Logger:

    print_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]

    @staticmethod
    def _print_log(level, color, msg):
        if level in Logger.print_levels:
            print(f"{color}[{level}] {msg}{Color.RESET}")

    @staticmethod
    def debug(msg):
        Logger._print_log("DEBUG", Color.BLUE, msg)

    @staticmethod
    def info(msg):
        Logger._print_log("INFO", Color.GREEN, msg)

    @staticmethod
    def warning(msg):
        Logger._print_log("WARNING", Color.YELLOW, msg)

    @staticmethod
    def error(msg):
        Logger._print_log("ERROR", Color.RED, msg)

if __name__ == "__main__":
    # log = Logger()
    Logger.debug("debug...")
    Logger.info("Info.")
    Logger.warning("warning.")
    Logger.error("error.")
    print("checking color is reset ...")

