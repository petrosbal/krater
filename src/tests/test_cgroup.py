import pytest
import cgroup

RUNC_ID = "a" * 64
SHIM_ID = "b" * 64
TWICE_ID = "d" * 64

def make_tree(root):
    # the two real layouts plus one ID that names two folders
    runc_pod = root / "kubepods.slice" / "kubepods-besteffort.slice" / "kubepods-besteffort-pod1.slice"
    (runc_pod / f"cri-containerd-{RUNC_ID}.scope").mkdir(parents=True)
    (root / f"kubepods-besteffort-pod2.slice:cri-containerd:{SHIM_ID}").mkdir()
    (root / "one" / f"x-{TWICE_ID}").mkdir(parents=True)
    (root / "two" / f"y-{TWICE_ID}").mkdir(parents=True)

def make_cgroup(folder, peak=True, kernel=True, nice=True, current="9000000\n", pids="3\n",
                pressure="some avg10=0.00 avg60=0.00 avg300=0.00 total=125000\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=99\n"):
    (folder / "cpu.stat").write_text(
        "usage_usec 2500000\nuser_usec 2000000\nsystem_usec 500000\n"
        + ("nice_usec 1500000\n" if nice else "")
        + "nr_periods 0\nthrottled_usec 250000\n")
    (folder / "memory.stat").write_text(
        "anon 6000000\nfile 1\n"
        + ("kernel 200000\n" if kernel else "")
        + "kernel_stack 50000\npgfault 1200\npgmajfault 3\n")
    (folder / "cpu.pressure").write_text(pressure)
    (folder / "pids.current").write_text(pids)
    if current is not None:
        (folder / "memory.current").write_text(current)
    if peak:
        (folder / "memory.peak").write_text("12000000\n")
    return folder

FIND_CGROUP_ROWS = {
    "runc layout, deep": (
        RUNC_ID,
        f"kubepods.slice/kubepods-besteffort.slice/kubepods-besteffort-pod1.slice/cri-containerd-{RUNC_ID}.scope",
    ),
    "shim layout, at the root": (
        SHIM_ID,
        f"kubepods-besteffort-pod2.slice:cri-containerd:{SHIM_ID}",
    ),
}

@pytest.mark.parametrize("container_id, expected",
    FIND_CGROUP_ROWS.values(), ids=FIND_CGROUP_ROWS.keys(),
)
def test_find_cgroup(tmp_path, container_id, expected):
    make_tree(tmp_path)
    assert cgroup.find_cgroup(container_id, tmp_path) == tmp_path / expected

FIND_CGROUP_REFUSALS = {
    "container exited": (
        "e" * 64,
        "found 0 matches for container 'eeeeeeeeeeee'",
    ),
    "two folders": (
        TWICE_ID,
        "found 2 matches for container 'dddddddddddd'",
    ),
    "empty id": (
        "",
        "container_id is empty",
    ),
}

@pytest.mark.parametrize("container_id, expected",
    FIND_CGROUP_REFUSALS.values(), ids=FIND_CGROUP_REFUSALS.keys(),
)
def test_find_cgroup_refuses(tmp_path, container_id, expected):
    make_tree(tmp_path)
    with pytest.raises(RuntimeError) as e:
        cgroup.find_cgroup(container_id, tmp_path)
    assert str(e.value) == expected

MISSING_FIELDS_ROWS = {
    "new kernel": (
        {},
        set(),
    ),
    "5.15 kernel": (
        {'peak': False, 'kernel': False, 'nice': False},
        {'peak_memory_bytes', 'kernel_memory_bytes', 'nice_seconds'},
    ),
    "only memory.peak missing": (
        {'peak': False},
        {'peak_memory_bytes'},
    ),
    "only the kernel line missing": (
        {'kernel': False},
        {'kernel_memory_bytes'},
    ),
    "only nice_usec missing": (
        {'nice': False},
        {'nice_seconds'},
    ),
}

@pytest.mark.parametrize("files, expected",
    MISSING_FIELDS_ROWS.values(), ids=MISSING_FIELDS_ROWS.keys(),
)
def test_missing_fields(tmp_path, files, expected):
    assert cgroup.missing_fields(make_cgroup(tmp_path, **files)) == expected

FULL_SAMPLE = {
    'cpu_seconds': 2.5,
    'user_seconds': 2.0,
    'system_seconds': 0.5,
    'throttled_seconds': 0.25,
    'cpu_wait_seconds': 0.125,
    'threads': 3,
    'memory_bytes': 9000000,
    'page_faults': 1200,
    'major_page_faults': 3,
    'anon_memory_bytes': 6000000,
    'kernel_memory_bytes': 200000,
    'nice_seconds': 1.5,
    'peak_memory_bytes': 12000000,
}

TAKE_SAMPLE_ROWS = {
    "new kernel": (
        {},
        set(),
        FULL_SAMPLE,
    ),
    "5.15 kernel": (
        {'peak': False, 'kernel': False, 'nice': False},
        {'peak_memory_bytes', 'kernel_memory_bytes', 'nice_seconds'},
        {**FULL_SAMPLE, 'kernel_memory_bytes': None, 'nice_seconds': None, 'peak_memory_bytes': None},
    ),
}

@pytest.mark.parametrize("files, missing, expected",
    TAKE_SAMPLE_ROWS.values(), ids=TAKE_SAMPLE_ROWS.keys(),
)
def test_take_sample(tmp_path, files, missing, expected):
    sample = cgroup.take_sample(make_cgroup(tmp_path, **files), missing)
    assert sample is not None
    del sample['timestamp']
    assert sample == expected

TAKE_SAMPLE_DROPS = {
    "container exited": {'current': None},
    "a value that isn't a number": {'pids': "max\n"},
    "empty cpu.pressure": {'pressure': ""},
    "memory.peak gone mid-trial": {'peak': False},
    "kernel line gone mid-trial": {'kernel': False},
    "nice_usec line gone mid-trial": {'nice': False},
}

@pytest.mark.parametrize(
    "files",
    TAKE_SAMPLE_DROPS.values(),
    ids=TAKE_SAMPLE_DROPS.keys(),
)
def test_take_sample_drops(tmp_path, files):
    assert cgroup.take_sample(make_cgroup(tmp_path, **files), set()) is None