"""Internal control signals that do not imply rollback of completed business work."""


class JobCancelled(Exception):
    pass


class JobInterrupted(Exception):
    pass
