# 自定义的exception

class Fail(Exception):
    """
    自定义业务触发，不需要追踪
    """
    def __init__(self, error_code, params=None, error_message=None):
        self.error_code = error_code
        self.params = params
        self.error_message = error_message

    def __str__(self):
        return self.error_code