from dvc.output.base import BaseOutput

from ..fs.gs import GSFileSystem


class GSOutput(BaseOutput):
    FS_CLS = GSFileSystem
