import logging

logger = logging.getLogger(__name__)


def _update_import_on_remote(stage, remote, jobs):
    url = stage.deps[0].path_info.url
    stage.outs[0].hash_info = stage.repo.cloud.transfer(
        url, jobs=jobs, remote=remote, command="update"
    )


def update_import(stage, rev=None, to_remote=False, remote=None, jobs=None):
    stage.deps[0].update(rev=rev)
    frozen = stage.frozen
    stage.frozen = False
    try:
        if to_remote:
            _update_import_on_remote(stage, remote, jobs)
        else:
            stage.reproduce(jobs=jobs)
    finally:
        stage.frozen = frozen


def sync_import(stage, dry=False, force=False, jobs=None):
    """Synchronize import's outs to the workspace."""
    logger.info(
        "Importing '{dep}' -> '{out}'".format(
            dep=stage.deps[0], out=stage.outs[0]
        )
    )
    if dry:
        return

    if not force and stage.already_cached():
        stage.outs[0].checkout()
    else:
        stage.save_deps()
        stage.deps[0].download(stage.outs[0], jobs=jobs)
