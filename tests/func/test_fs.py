import os
from operator import itemgetter
from os.path import join

import pytest

from dvc.fs import get_cloud_fs
from dvc.fs.local import LocalFileSystem
from dvc.path_info import PathInfo
from dvc.repo import Repo
from dvc.scm import SCM
from tests.basic_env import TestDir, TestGit, TestGitSubmodule


class TestLocalFileSystem(TestDir):
    def setUp(self):
        super().setUp()
        self.fs = LocalFileSystem(None, {})

    def test_open(self):
        with self.fs.open(self.FOO) as fd:
            self.assertEqual(fd.read(), self.FOO_CONTENTS)
        with self.fs.open(self.UNICODE, encoding="utf-8") as fd:
            self.assertEqual(fd.read(), self.UNICODE_CONTENTS)

    def test_exists(self):
        self.assertTrue(self.fs.exists(self.FOO))
        self.assertTrue(self.fs.exists(self.UNICODE))
        self.assertFalse(self.fs.exists("not-existing-file"))

    def test_isdir(self):
        self.assertTrue(self.fs.isdir(self.DATA_DIR))
        self.assertFalse(self.fs.isdir(self.FOO))
        self.assertFalse(self.fs.isdir("not-existing-file"))

    def test_isfile(self):
        self.assertTrue(self.fs.isfile(self.FOO))
        self.assertFalse(self.fs.isfile(self.DATA_DIR))
        self.assertFalse(self.fs.isfile("not-existing-file"))


class GitFileSystemTests:
    # pylint: disable=no-member
    def test_open(self):
        self.scm.add([self.FOO, self.UNICODE, self.DATA_DIR])
        self.scm.commit("add")

        fs = self.scm.get_fs("master")
        with fs.open(self.FOO) as fd:
            self.assertEqual(fd.read(), self.FOO_CONTENTS)
        with fs.open(self.UNICODE) as fd:
            self.assertEqual(fd.read(), self.UNICODE_CONTENTS)
        with self.assertRaises(IOError):
            fs.open("not-existing-file")
        with self.assertRaises(IOError):
            fs.open(self.DATA_DIR)

    def test_exists(self):
        fs = self.scm.get_fs("master")
        self.assertFalse(fs.exists(self.FOO))
        self.assertFalse(fs.exists(self.UNICODE))
        self.assertFalse(fs.exists(self.DATA_DIR))
        self.scm.add([self.FOO, self.UNICODE, self.DATA])
        self.scm.commit("add")

        fs = self.scm.get_fs("master")
        self.assertTrue(fs.exists(self.FOO))
        self.assertTrue(fs.exists(self.UNICODE))
        self.assertTrue(fs.exists(self.DATA_DIR))
        self.assertFalse(fs.exists("non-existing-file"))

    def test_isdir(self):
        self.scm.add([self.FOO, self.DATA_DIR])
        self.scm.commit("add")

        fs = self.scm.get_fs("master")
        self.assertTrue(fs.isdir(self.DATA_DIR))
        self.assertFalse(fs.isdir(self.FOO))
        self.assertFalse(fs.isdir("non-existing-file"))

    def test_isfile(self):
        self.scm.add([self.FOO, self.DATA_DIR])
        self.scm.commit("add")

        fs = self.scm.get_fs("master")
        self.assertTrue(fs.isfile(self.FOO))
        self.assertFalse(fs.isfile(self.DATA_DIR))
        self.assertFalse(fs.isfile("not-existing-file"))


class TestGitFileSystem(TestGit, GitFileSystemTests):
    def setUp(self):
        super().setUp()
        self.scm = SCM(self._root_dir)


class TestGitSubmoduleFileSystem(TestGitSubmodule, GitFileSystemTests):
    def setUp(self):
        super().setUp()
        self.scm = SCM(self._root_dir)
        self._pushd(self._root_dir)


class AssertWalkEqualMixin:
    def assertWalkEqual(self, actual, expected, msg=None):
        def convert_to_sets(walk_results):
            return [
                (root, set(dirs), set(nondirs))
                for root, dirs, nondirs in walk_results
            ]

        self.assertEqual(
            convert_to_sets(actual), convert_to_sets(expected), msg=msg
        )


class TestWalkInNoSCM(AssertWalkEqualMixin, TestDir):
    def test(self):
        fs = LocalFileSystem(None, {"url": self._root_dir})
        self.assertWalkEqual(
            fs.walk(self._root_dir),
            [
                (
                    self._root_dir,
                    ["data_dir"],
                    ["code.py", "bar", "тест", "foo"],
                ),
                (join(self._root_dir, "data_dir"), ["data_sub_dir"], ["data"]),
                (
                    join(self._root_dir, "data_dir", "data_sub_dir"),
                    [],
                    ["data_sub"],
                ),
            ],
        )

    def test_subdir(self):
        fs = LocalFileSystem(None, {"url": self._root_dir})
        self.assertWalkEqual(
            fs.walk(join("data_dir", "data_sub_dir")),
            [(join("data_dir", "data_sub_dir"), [], ["data_sub"])],
        )


class TestWalkInGit(AssertWalkEqualMixin, TestGit):
    def test_nobranch(self):
        fs = LocalFileSystem(None, {"url": self._root_dir}, use_dvcignore=True)
        self.assertWalkEqual(
            fs.walk("."),
            [
                (".", ["data_dir"], ["bar", "тест", "code.py", "foo"]),
                (join("data_dir"), ["data_sub_dir"], ["data"]),
                (join("data_dir", "data_sub_dir"), [], ["data_sub"]),
            ],
        )
        self.assertWalkEqual(
            fs.walk(join("data_dir", "data_sub_dir")),
            [(join("data_dir", "data_sub_dir"), [], ["data_sub"])],
        )

    def test_branch(self):
        scm = SCM(self._root_dir)
        scm.add([self.DATA_SUB_DIR])
        scm.commit("add data_dir/data_sub_dir/data_sub")
        fs = scm.get_fs("master")
        self.assertWalkEqual(
            fs.walk("."),
            [
                (self._root_dir, ["data_dir"], ["code.py"]),
                (join(self._root_dir, "data_dir"), ["data_sub_dir"], []),
                (
                    join(self._root_dir, "data_dir", "data_sub_dir"),
                    [],
                    ["data_sub"],
                ),
            ],
        )
        self.assertWalkEqual(
            fs.walk(join("data_dir", "data_sub_dir")),
            [
                (
                    join(self._root_dir, "data_dir", "data_sub_dir"),
                    [],
                    ["data_sub"],
                )
            ],
        )


def test_cleanfs_subrepo(tmp_dir, dvc, scm, monkeypatch):
    tmp_dir.gen({"subdir": {}})
    subrepo_dir = tmp_dir / "subdir"
    with subrepo_dir.chdir():
        subrepo = Repo.init(subdir=True)
        subrepo_dir.gen({"foo": "foo", "dir": {"bar": "bar"}})

    path = PathInfo(subrepo_dir)

    assert dvc.fs.use_dvcignore
    assert not dvc.fs.exists(path / "foo")
    assert not dvc.fs.isfile(path / "foo")
    assert not dvc.fs.exists(path / "dir")
    assert not dvc.fs.isdir(path / "dir")

    assert subrepo.fs.use_dvcignore
    assert subrepo.fs.exists(path / "foo")
    assert subrepo.fs.isfile(path / "foo")
    assert subrepo.fs.exists(path / "dir")
    assert subrepo.fs.isdir(path / "dir")


def test_walk_dont_ignore_subrepos(tmp_dir, scm, dvc):
    tmp_dir.dvc_gen({"foo": "foo"}, commit="add foo")
    subrepo_dir = tmp_dir / "subdir"
    subrepo_dir.mkdir()
    with subrepo_dir.chdir():
        Repo.init(subdir=True)
    scm.add(["subdir"])
    scm.commit("Add subrepo")

    dvc_fs = dvc.fs
    dvc_fs._reset()
    scm_fs = scm.get_fs("HEAD", use_dvcignore=True)
    path = os.fspath(tmp_dir)
    get_dirs = itemgetter(1)

    assert get_dirs(next(dvc_fs.walk(path))) == []
    assert get_dirs(next(scm_fs.walk(path))) == []

    kw = {"ignore_subrepos": False}
    assert get_dirs(next(dvc_fs.walk(path, **kw))) == ["subdir"]
    assert get_dirs(next(scm_fs.walk(path, **kw))) == ["subdir"]


@pytest.mark.parametrize(
    "cloud",
    [
        pytest.lazy_fixture("local_cloud"),
        pytest.lazy_fixture("s3"),
        pytest.lazy_fixture("gs"),
        pytest.lazy_fixture("hdfs"),
        pytest.lazy_fixture("http"),
    ],
)
def test_fs_getsize(dvc, cloud):
    cloud.gen({"data": {"foo": "foo"}, "baz": "baz baz"})
    fs = get_cloud_fs(dvc, **cloud.config)
    path_info = fs.path_info

    assert fs.getsize(path_info / "baz") == 7
    assert fs.getsize(path_info / "data" / "foo") == 3


@pytest.mark.parametrize(
    "cloud",
    [
        pytest.lazy_fixture("azure"),
        pytest.lazy_fixture("gs"),
        pytest.lazy_fixture("gdrive"),
        pytest.lazy_fixture("hdfs"),
        pytest.lazy_fixture("http"),
        pytest.lazy_fixture("local_cloud"),
        pytest.lazy_fixture("oss"),
        pytest.lazy_fixture("s3"),
        pytest.lazy_fixture("ssh"),
        pytest.lazy_fixture("webhdfs"),
    ],
)
def test_fs_upload_fobj(dvc, tmp_dir, cloud):
    tmp_dir.gen("foo", "foo")
    fs = get_cloud_fs(dvc, **cloud.config)

    from_info = tmp_dir / "foo"
    to_info = fs.path_info / "foo"

    with open(from_info, "rb") as stream:
        fs.upload_fobj(stream, to_info)

    assert fs.exists(to_info)
    with fs.open(to_info, "rb") as stream:
        assert stream.read() == b"foo"


@pytest.mark.parametrize("cloud", [pytest.lazy_fixture("gdrive")])
def test_fs_ls(dvc, cloud):
    cloud.gen(
        {
            "directory": {
                "foo": "foo",
                "bar": "bar",
                "baz": {"quux": "quux", "egg": {"foo": "foo"}},
                "empty": {},
            }
        }
    )
    fs = get_cloud_fs(dvc, **cloud.config)
    path_info = cloud / "directory"

    assert {os.path.basename(file_key) for file_key in fs.ls(path_info)} == {
        "foo",
        "bar",
        "baz",
        "empty",
    }
    assert set(fs.ls(path_info / "empty")) == set()
    assert {
        (detail["type"], os.path.basename(detail["name"]))
        for detail in fs.ls(path_info / "baz", detail=True)
    } == {("file", "quux"), ("directory", "egg")}


@pytest.mark.parametrize(
    "cloud",
    [
        pytest.lazy_fixture("s3"),
        pytest.lazy_fixture("azure"),
        pytest.lazy_fixture("gs"),
        pytest.lazy_fixture("webdav"),
        pytest.lazy_fixture("gdrive"),
    ],
)
def test_fs_ls_recursive(dvc, cloud):
    cloud.gen({"data": {"foo": "foo", "bar": {"baz": "baz"}, "quux": "quux"}})
    fs = get_cloud_fs(dvc, **cloud.config)
    path_info = fs.path_info

    assert {
        os.path.basename(file_key)
        for file_key in fs.ls(path_info / "data", recursive=True)
    } == {"foo", "baz", "quux"}


@pytest.mark.parametrize(
    "cloud",
    [
        pytest.lazy_fixture("s3"),
        pytest.lazy_fixture("azure"),
        pytest.lazy_fixture("gs"),
        pytest.lazy_fixture("webdav"),
    ],
)
def test_fs_ls_with_etag(dvc, cloud):
    cloud.gen({"data": {"foo": "foo", "bar": {"baz": "baz"}, "quux": "quux"}})
    fs = get_cloud_fs(dvc, **cloud.config)
    path_info = fs.path_info

    for details in fs.ls(path_info / "data", recursive=True, detail=True):
        assert (
            fs.info(path_info.replace(path=details["name"]))["etag"]
            == details["etag"]
        )
