#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M6 发布终态自检（离线 + --online 两模）。

用法（在仓库根目录）：
    python scripts/check_release.py                     # 离线：tag / 留档 / 附件本地副本 / README / 脱敏 / 工作树
    python scripts/check_release.py --online            # 追加：远端 tag / Release 资产 / CI 四矩阵 / topics
    python scripts/check_release.py --pre-tag           # tag 前冒烟：跳过 tag 相关项
    python scripts/check_release.py --json              # 机器可读输出

退出码：0 = 无 FAIL（WARN / SKIP 允许）；1 = 有 FAIL；2 = 用法错误。

设计口径（plan/00 §四 M6 行、plan/05 M6 DoD、HANDOFF-M6 §2）：
- K30：发布留档 `plan/RELEASE-M6.md` 必须在 tag 之前入库，且分栏
  "tag 时点事实 / tag 后追加事实"；tag 后只允许追加类提交。
- K31：Release 附件必须手工上传（>=1 个），本地留副本 + sha256；
  源码 zipball 不算产物。
- K33：全仓（工作树 + 全历史）不得出现本机绝对路径 / 用户名 / 邮箱 /
  本系列其他项目名；扫描必须带阳性对照，防"扫了 0 命中"与"扫描没工作"混淆。

本脚本只做可机械判定的部分；人工项（竞品事实复核、题面 vs 数据台账对撞）
不在脚本范围内。
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

def package_version(repo):
    """版本号唯一出处：scripts/chartaudit/__init__.py。tag / 附件名由它派生，不再写第三份字面量。"""
    init_py = read_text(os.path.join(repo, "scripts", "chartaudit", "__init__.py"))
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', init_py, re.M)
    return match.group(1).strip() if match else ""


def readme_status(text, version):
    """判定 README 里当前版本的状态：'published' / 'unshipped' / None。

    必须是"当前包版本 + 已发布"同句；"v0.1.1 已就绪待发布"这类句子判成 unshipped，
    不能拿它糊过去（v0.1.0.dev0 那轮的教训：README 说 v0.1.0，包却是 0.1.0.dev0）。
    """
    if not version:
        return None
    state = None
    for match in re.finditer(r"v%s([^。\n]{0,40})" % re.escape(version), text):
        tail = match.group(1)
        if re.search(r"[待未]发布|尚[未不]", tail):
            state = "unshipped"
        elif "已发布" in tail:
            return "published"
    return state


def section_after(text, heading):
    """取 `heading` 所在行起、到下一个同级标题之前的片段（含标题行本身）。"""
    start = text.index(heading)
    rest = text[start + len(heading):]
    nxt = re.search(r"^#{1,2}\s", rest, re.M)
    return text[start:start + len(heading)] + (rest[:nxt.start()] if nxt else rest)



REPO_DEFAULT = "yuluo554/10-18-truth-chart-skill"
RELEASE_DOC = "plan/RELEASE-M6.md"   # 由 resolve_release_names() 按版本改指
SCAN_DOC = "plan/M6-desensitize-scan.md"
VERIFY_DOC = "plan/verify/README.md"
LOCAL_RELEASE_DIR = "release"

# tag / 附件名 / 发布留档名的默认值在 main() 里由 package_version(repo) 派生
# （见 resolve_release_names），不在脚本里写第二份版本字面量——改版本只需改 __init__.py 一处。
TAG_DEFAULT = ""
ATTACHMENT = ""


def resolve_release_names(repo, tag):
    """把 tag / 附件名 / 发布留档名解析成当前仓库版本对应的形态。"""
    global TAG_DEFAULT, ATTACHMENT, RELEASE_DOC
    version = package_version(repo)
    if version:
        TAG_DEFAULT = "v%s" % version
        ATTACHMENT = "chartaudit-v%s-samples.zip" % version
        per_version_doc = "plan/RELEASE-v%s.md" % version
        if os.path.isfile(os.path.join(repo, per_version_doc)):
            RELEASE_DOC = per_version_doc
        if not tag:
            tag = TAG_DEFAULT
    return tag

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"
RESULTS = []


def add(level, code, message):
    RESULTS.append({"level": level, "code": code, "message": message})


def run(args, cwd=None, timeout=45):
    env = dict(os.environ)
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o ConnectTimeout=8")
    env.setdefault("GIT_HTTP_LOW_SPEED_LIMIT", "1000")
    env.setdefault("GIT_HTTP_LOW_SPEED_TIME", "8")
    try:
        proc = subprocess.run(
            args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout, env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "timeout/error: %s" % exc
    return proc.returncode, proc.stdout.decode("utf-8", "replace").strip()


def git(repo, *args):
    return run(["git", "-C", repo] + list(args))


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def current_username():
    for key in ("USERNAME", "USER", "LOGNAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def is_noreply_email(value):
    value = (value or "").strip().strip("<>").lower()
    return bool(re.match(r"^(?:\d+\+)?[^@]+@users\.noreply\.github\.com$", value))


# ---------------------------------------------------------------- 本地 tag 面

def check_repo(repo):
    rc, top = git(repo, "rev-parse", "--show-toplevel")
    if rc != 0:
        add(FAIL, "GIT_REPO", "当前目录不是 git 仓库：%s" % top[:120])
        return False
    top = os.path.realpath(top)
    if os.path.realpath(repo) != top:
        add(WARN, "GIT_REPO", "脚本不在仓库根目录运行（repo=%s）" % top)
    else:
        add(PASS, "GIT_REPO", "仓库根目录：%s" % top)
    return True


def tag_commit(repo, tag):
    rc, out = git(repo, "rev-list", "-n", "1", tag)
    return out.strip() if rc == 0 else ""


def check_tag(repo, tag, pre_tag):
    if pre_tag:
        add(SKIP, "TAG_EXISTS", "--pre-tag：跳过 tag 检查")
        return
    rc, _ = git(repo, "rev-parse", "--verify", "refs/tags/%s" % tag)
    if rc != 0:
        add(FAIL, "TAG_EXISTS", "tag %s 不存在" % tag)
        return
    add(PASS, "TAG_EXISTS", "tag %s 存在" % tag)

    rc, kind = git(repo, "cat-file", "-t", tag)
    if kind.strip() == "tag":
        add(PASS, "TAG_ANNOTATED", "tag %s 是 annotated tag（有 tagger 元数据）" % tag)
    else:
        add(WARN, "TAG_ANNOTATED", "tag %s 是轻量 tag；建议 -a 并确认 tagger 邮箱已脱敏" % tag)

    rc, files = git(repo, "-c", "core.quotepath=false", "ls-tree", "-r", "--name-only", tag)
    tree_files = files.splitlines() if rc == 0 else []
    required = [RELEASE_DOC, SCAN_DOC, VERIFY_DOC, "scripts/check_release.py", "README.md"]
    missing = [name for name in required if name not in tree_files]
    if missing:
        add(FAIL, "TAG_TREE_DOCS", "tag 树缺发布留档/门禁文件：%s" % ", ".join(missing))
    else:
        add(PASS, "TAG_TREE_DOCS",
            "tag 树含留档/脱敏/验证/发布门禁（%d 个文件）" % len(tree_files))

    rc, body = git(repo, "show", "%s:README.md" % tag)
    if rc != 0:
        add(FAIL, "TAG_README", "tag 树无 README.md")
    else:
        stale = re.search(r"开发中|未开工|M6\s*发布未|待首推|发布执行中", body)
        version = tag.lstrip("v")
        state = readme_status(body, version)
        if stale:
            add(FAIL, "TAG_README", "tag 树 README 仍为未发布态（命中：%s）" % stale.group(0))
        elif state == "published":
            add(PASS, "TAG_README", "tag 树 README 为 v%s 发布态" % version)
        elif state == "unshipped":
            add(FAIL, "TAG_README", "tag 树 README 仍写 v%s 未发布（tag 已打，属自相矛盾）" % version)
        else:
            add(WARN, "TAG_README", "tag 树 README 未找到 v%s 的明确发布状态行" % version)

    rc, body = git(repo, "show", "%s:%s" % (tag, RELEASE_DOC))
    if rc != 0:
        add(FAIL, "TAG_RELEASE_DOC", "tag 树无 %s" % RELEASE_DOC)
    else:
        has_before = re.search(r"tag\s*时点事实", body)
        has_after = re.search(r"tag\s*后追加事实", body)
        if has_before and has_after:
            add(PASS, "TAG_RELEASE_DOC", "tag 树发布留档已分栏（tag 时点 / tag 后追加）")
        else:
            add(FAIL, "TAG_RELEASE_DOC", "tag 树发布留档缺分栏标题")

    rc, body = git(repo, "show", "%s:plan/05-里程碑.md" % tag)
    if rc == 0 and re.search(r"##\s*M6\s*发布", body):
        m6 = body[body.index("## M6 发布"):]
        # tag 时点允许写"执行中/Release 待补"，但 tag 树里不能把未完成项写成已完成；
        # 最终态由 check_m6_checklist() 在当前工作树判定。
        add(PASS, "TAG_M6_SECTION", "tag 树 plan/05 含 M6 小节")
    else:
        add(WARN, "TAG_M6_SECTION", "tag 树 plan/05 无 M6 小节")


def check_post_tag(repo, tag, pre_tag):
    if pre_tag:
        add(SKIP, "POST_TAG", "--pre-tag：跳过 post-tag 检查")
        return
    rc, out = git(repo, "log", "--oneline", "%s..HEAD" % tag)
    if rc != 0:
        add(WARN, "POST_TAG", "无法读取 tag..HEAD")
        return
    commits = [line for line in out.splitlines() if line.strip()]
    if not commits:
        add(PASS, "POST_TAG", "HEAD == tag（tag 后无提交）")
    else:
        allowed = re.compile(r"回写|补记|对账|留档|追加|收口|复核|校准|快照|终记|订正|发布")
        offenders = [line for line in commits if not allowed.search(line)]
        if offenders:
            add(WARN, "POST_TAG", "tag 后有非追加类提交措辞：%s" % offenders[0][:100])
        else:
            add(PASS, "POST_TAG", "tag 后 %d 个提交均为追加类措辞" % len(commits))

    rc, out = git(repo, "-c", "core.quotepath=false", "diff", "--name-only", "%s..HEAD" % tag)
    if rc != 0:
        add(WARN, "POST_TAG_FILES", "无法读取 tag..HEAD 文件差异")
        return
    changed = [line.strip().strip('"') for line in out.splitlines() if line.strip()]
    if not changed:
        add(PASS, "POST_TAG_FILES", "tag 后无文件改动")
        return
    allowed_paths = ("plan/",)
    allowed_files = ("README.md", ".gitignore", "scripts/check_release.py")
    hard = [path for path in changed
            if not path.startswith(allowed_paths) and path not in allowed_files]
    if hard:
        add(FAIL, "POST_TAG_FILES",
            "tag 后改动产品/构建面文件：%s —— tag 打早了或发布物与源码不一致"
            % ", ".join(hard[:6]))
    else:
        add(PASS, "POST_TAG_FILES", "tag 后改动仅限文档/发布门禁（%d 个文件）" % len(changed))


# ---------------------------------------------------------------- 工作树文档面

def check_worktree(repo):
    rc, out = git(repo, "status", "--porcelain")
    if rc != 0:
        add(FAIL, "CLEAN_TREE", "无法读取 git status")
    elif out.strip():
        add(FAIL, "CLEAN_TREE", "工作树不干净（%d 项）" % len(out.splitlines()))
    else:
        add(PASS, "CLEAN_TREE", "工作树干净")

    body = read_text(os.path.join(repo, "README.md"))
    head = "\n".join(body.splitlines()[:12])
    stale = re.search(r"开发中|未开工|M6\s*发布未|待首推|发布执行中", head)
    version = package_version(repo)
    state = readme_status(head, version)
    if stale:
        add(FAIL, "README_STATUS", "README 状态行仍为未发布态（命中：%s）" % stale.group(0))
    elif not version:
        add(FAIL, "README_STATUS", "无法读取包版本号，无法判定 README 状态行")
    elif state == "published":
        add(PASS, "README_STATUS", "README 状态行为 v%s 发布态" % version)
    elif state == "unshipped":
        add(WARN, "README_STATUS", "README 明写 v%s 尚未发布（tag 未打时的应有形态）" % version)
    else:
        add(WARN, "README_STATUS", "README 前 12 行未找到 v%s 的已发布状态行" % version)

    plan05 = read_text(os.path.join(repo, "plan", "05-里程碑.md"))
    if "## M6 发布" in plan05:
        m6 = section_after(plan05, "## M6 发布")
        open_items = re.findall(r"^\s*-\s*\[ \]", m6, re.M)
        done_status = re.search(r"M6\s*发布\s*[—\-]\s*状态：\s*✅", m6)
        if open_items:
            add(FAIL, "M6_CHECKLIST", "plan/05 M6 仍有 %d 个未勾选项" % len(open_items))
        elif done_status:
            add(PASS, "M6_CHECKLIST", "plan/05 M6 已完成态且无未勾选项")
        else:
            add(WARN, "M6_CHECKLIST", "plan/05 M6 无未勾选项但状态行不是 ✅")
    else:
        add(FAIL, "M6_CHECKLIST", "plan/05 无 M6 小节")

    plan00 = read_text(os.path.join(repo, "plan", "00-README总览.md"))
    milestone = re.search(r"当前里程碑[^\n]*", plan00)
    if milestone:
        line = milestone.group(0)
        if "M6" in line and "✅" in line and "未开工" not in line:
            add(PASS, "PLAN00_MILESTONE", "plan/00 当前里程碑已翻转 M6 ✅")
        else:
            add(WARN, "PLAN00_MILESTONE", "plan/00 当前里程碑行未明确 M6 ✅：%s" % line[:100])
    else:
        add(WARN, "PLAN00_MILESTONE", "plan/00 未找到当前里程碑行")

    plan06 = read_text(os.path.join(repo, "plan", "06-交付对标与决策记录.md"))
    if re.search(r"清零状态[^\n]*M6[^\n]*收口", plan06) or \
       re.search(r"Q1/Q2[^\n]*(已清零|落档|不再悬挂|已执行)", plan06):
        add(PASS, "PLAN06_Q1Q2", "plan/06 Q1/Q2 已清零或已落档")
    else:
        add(WARN, "PLAN06_Q1Q2", "plan/06 Q1/Q2 未见清零/落档语句")


def check_version(repo):
    """版本口径唯一性：pyproject 与 __init__ 两处相等且均不含 dev 段。

    D1 回归守门：只改一处 → 不相等；两处都写 .dev0 → 含 dev 段；各自独立变红。
    """
    pyproject = read_text(os.path.join(repo, "pyproject.toml"))
    init_py = read_text(os.path.join(repo, "scripts", "chartaudit", "__init__.py"))
    py_match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', pyproject, re.M)
    init_match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', init_py, re.M)
    if not py_match:
        add(FAIL, "VERSION", "pyproject.toml 未找到 version 字段")
        return
    if not init_match:
        add(FAIL, "VERSION", "scripts/chartaudit/__init__.py 未找到 __version__")
        return
    py_version = py_match.group(1).strip()
    init_version = init_match.group(1).strip()
    if py_version != init_version:
        add(FAIL, "VERSION",
            "版本号不一致：pyproject=%s / __init__=%s" % (py_version, init_version))
        return
    dev_re = re.compile(r"\.?dev\d*", re.I)
    dev_hits = [value for value in (py_version, init_version) if dev_re.search(value)]
    if dev_hits:
        add(FAIL, "VERSION",
            "版本号含 dev 段（PEP 440 语义排在正式版之前）：%s" % dev_hits[0])
        return
    add(PASS, "VERSION",
        "pyproject 与 __init__ 版本号一致且无 dev 段（%s）" % py_version)


def check_docs(repo):
    release_doc = read_text(os.path.join(repo, RELEASE_DOC))
    if not release_doc:
        add(FAIL, "RELEASE_DOC", "缺 %s" % RELEASE_DOC)
    else:
        has_before = re.search(r"tag\s*时点事实", release_doc)
        has_after = re.search(r"tag\s*后追加事实", release_doc)
        if has_before and has_after:
            add(PASS, "RELEASE_DOC", "发布留档存在且分栏（tag 时点 / tag 后追加）")
        else:
            add(FAIL, "RELEASE_DOC", "发布留档缺分栏标题")

    scan_doc = read_text(os.path.join(repo, SCAN_DOC))
    if not scan_doc:
        add(FAIL, "SCAN_DOC", "缺脱敏扫描留档 %s" % SCAN_DOC)
    elif "0 命中" in scan_doc and "全历史" in scan_doc and "阳性对照" in scan_doc:
        add(PASS, "SCAN_DOC", "脱敏扫描留档含工作树/全历史/阳性对照结论")
    else:
        add(WARN, "SCAN_DOC", "脱敏扫描留档字段不完整（需含 0 命中 / 全历史 / 阳性对照）")

    verify_doc = read_text(os.path.join(repo, VERIFY_DOC))
    version = package_version(repo)
    if not verify_doc:
        add(FAIL, "VERIFY_DOC", "缺干净环境验证留档 %s" % VERIFY_DOC)
    elif "3.12" not in verify_doc:
        add(FAIL, "VERIFY_DOC", "干净环境验证留档未记录 3.12 通道")
    elif version and ("v" + version) not in verify_doc:
        add(WARN, "VERIFY_DOC",
            "干净环境验证留档没有 v%s 段落（当前版本未在本版干净环境里实跑过）" % version)
    else:
        add(PASS, "VERIFY_DOC", "干净环境验证留档含 3.12 通道与 v%s 段落" % version)


# ---------------------------------------------------------------- 附件面

def check_local_attachment(repo):
    local_dir = os.path.join(repo, LOCAL_RELEASE_DIR)
    path = os.path.join(local_dir, ATTACHMENT)
    if not os.path.isfile(path):
        add(FAIL, "LOCAL_ATTACHMENT", "缺本地附件副本 %s/%s" % (LOCAL_RELEASE_DIR, ATTACHMENT))
        return None
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
    except (OSError, zipfile.BadZipFile) as exc:
        add(FAIL, "LOCAL_ATTACHMENT", "附件不是合法 zip：%s" % exc)
        return None
    required = ("clean_bar.html", "g2_skewed.audit.html")
    missing = [name for name in required if not any(n.endswith(name) for n in names)]
    if missing:
        add(FAIL, "LOCAL_ATTACHMENT", "附件缺样例文件：%s" % ", ".join(missing))
        return None
    digest = sha256_file(path)
    add(PASS, "LOCAL_ATTACHMENT",
        "本地附件存在（%d 字节，sha256=%s，含 %d 个文件）"
        % (os.path.getsize(path), digest[:16] + "…", len(names)))

    sums_path = os.path.join(local_dir, "SHA256SUMS")
    sums = read_text(sums_path)
    if not sums:
        add(FAIL, "ATTACHMENT_SHA256", "缺 %s/SHA256SUMS" % LOCAL_RELEASE_DIR)
    else:
        recorded = None
        for line in sums.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[-1].lstrip("*") == ATTACHMENT:
                recorded = parts[0].lower()
                break
        if recorded == digest:
            add(PASS, "ATTACHMENT_SHA256", "本地附件 sha256 与 SHA256SUMS 一致")
        else:
            add(FAIL, "ATTACHMENT_SHA256",
                "本地附件 sha256 与 SHA256SUMS 不一致（记录=%s，实算=%s）"
                % ((recorded or "缺")[:16], digest[:16]))

    release_doc = read_text(os.path.join(repo, RELEASE_DOC))
    if digest in release_doc.lower():
        add(PASS, "ATTACHMENT_DOC_HASH", "发布留档记录了附件 sha256")
    else:
        add(FAIL, "ATTACHMENT_DOC_HASH", "发布留档未记录附件 sha256")

    rc, out = git(repo, "ls-files", "--", LOCAL_RELEASE_DIR)
    if rc == 0 and out.strip():
        add(FAIL, "ATTACHMENT_TRACKED", "本地附件目录已入库：%s" % out.splitlines()[0])
    else:
        add(PASS, "ATTACHMENT_TRACKED", "本地附件目录未入库（本地副本）")

    gitignore = read_text(os.path.join(repo, ".gitignore"))
    if re.search(r"^%s/?$" % re.escape(LOCAL_RELEASE_DIR), gitignore, re.M):
        add(PASS, "ATTACHMENT_IGNORED", ".gitignore 已忽略 %s/" % LOCAL_RELEASE_DIR)
    else:
        add(WARN, "ATTACHMENT_IGNORED", ".gitignore 未忽略 %s/（有误入库风险）" % LOCAL_RELEASE_DIR)
    return digest


# ---------------------------------------------------------------- 脱敏面

def check_commit_emails(repo):
    rc, out = git(repo, "log", "--format=%ae%n%ce")
    if rc != 0:
        add(WARN, "COMMIT_EMAILS", "无法读取提交邮箱")
        return
    emails = sorted({line.strip() for line in out.splitlines() if line.strip()})
    bad = [email for email in emails if not is_noreply_email(email)]
    if bad:
        add(FAIL, "COMMIT_EMAILS", "提交邮箱非 GitHub noreply：%s" % ", ".join(bad[:4]))
    else:
        add(PASS, "COMMIT_EMAILS", "全部提交邮箱为 noreply（%d 个唯一值）" % len(emails))


def check_tagger_email(repo, tag, pre_tag):
    if pre_tag:
        add(SKIP, "TAGGER_EMAIL", "--pre-tag：跳过 tagger 检查")
        return
    rc, out = git(repo, "for-each-ref", "refs/tags/%s" % tag, "--format=%(taggeremail)")
    if rc != 0 or not out.strip():
        add(WARN, "TAGGER_EMAIL", "无法读取 tagger 邮箱（轻量 tag 或 tag 不存在）")
        return
    email = out.strip().strip("<>")
    if is_noreply_email(email):
        add(PASS, "TAGGER_EMAIL", "tag tagger 邮箱为 noreply")
    else:
        add(FAIL, "TAGGER_EMAIL", "tag tagger 邮箱非 noreply：%s" % email)


DRIVE_ABS_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/](?:Users|ProgramData|Documents and Settings)[\\/]")
MSYS_ABS_RE = re.compile(r"(?<![A-Za-z0-9])/[A-Za-z]/(?:Users|ProgramData|home)/")
USERS_PATH_RE = re.compile(r"[\\/]Users[\\/]([^\\/\"'`\s]+)")
HOME_PATH_RE = re.compile(r"(?<![A-Za-z0-9])/home/([^/\s\"'`]+)")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
TOKEN_RE = re.compile(r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,})")
PRIVATE_KEY_RE = re.compile(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY")
GENERIC_USERS = {
    "public", "default", "default user", "runner", "runneradmin", "user",
    "username", "example", "test", "foo", "bar", "xxx", "yourname",
    "zhangsan", "lisi", "wangwu", "张三", "李四", "王五",
}


def _tracked_files(repo):
    rc, out = git(repo, "-c", "core.quotepath=false", "ls-files")
    if rc != 0:
        return []
    return [line for line in out.splitlines() if line.strip()]


def check_tracked_leaks(repo):
    files = _tracked_files(repo)
    if not files:
        add(FAIL, "TRACKED_LEAKS", "git ls-files 为 0 个文件——扫描面为空，不能判绿")
        return
    username = current_username()
    hits = []
    scanned = 0
    for rel in files:
        path = os.path.join(repo, rel)
        if not os.path.isfile(path):
            continue
        # 扫描器自身的模式定义行不是泄露（自引用）；命中以"非自引用"为准
        is_scanner = rel == "scripts/check_release.py"
        try:
            if os.path.getsize(path) > 2 * 1024 * 1024:
                continue
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except OSError:
            continue
        scanned += 1
        if not is_scanner:
            if DRIVE_ABS_RE.search(text) or MSYS_ABS_RE.search(text):
                hits.append("绝对路径:" + rel)
            if "ProgramData" + os.sep + "zcode" in text or "ProgramData/zcode" in text:
                hits.append("工作区标记:" + rel)
            for match in USERS_PATH_RE.finditer(text):
                name = match.group(1).strip(".,;:`'\"()[]")
                if name and name.lower() not in GENERIC_USERS:
                    hits.append("用户目录:" + rel)
            for match in HOME_PATH_RE.finditer(text):
                name = match.group(1).strip(".,;:`'\"()[]")
                if name and name.lower() not in GENERIC_USERS:
                    hits.append("home 目录:" + rel)
        if username and len(username) >= 3 and re.search(
                r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(username), text, re.I):
            hits.append("系统用户名:" + rel)
        for match in EMAIL_RE.finditer(text):
            email = match.group(0)
            if email.lower() == "git@github.com":
                continue
            if is_noreply_email(email):
                continue
            # 测试夹具里的占位邮箱（RFC 2606 保留域）不是真实身份泄露
            if re.match(r"^[A-Za-z0-9._%+-]+@(example\.(?:com|org|net)|test|invalid)$", email, re.I):
                continue
            hits.append("邮箱:" + rel)
        if TOKEN_RE.search(text) or PRIVATE_KEY_RE.search(text):
            hits.append("凭据:" + rel)
    if hits:
        unique = sorted(set(hits))
        add(FAIL, "TRACKED_LEAKS",
            "入库文件命中 %d 处（词面不回显）：%s" % (len(unique), ", ".join(unique[:6])))
    else:
        add(PASS, "TRACKED_LEAKS",
            "入库文件 0 命中（扫描 %d 个文本文件；绝对路径/用户名/邮箱/凭据）" % scanned)


def check_history_leaks(repo):
    """全历史 blob 扫描；带阳性对照，防 git grep 多 rev 静默空扫。"""
    rc, revs = git(repo, "rev-list", "--all")
    if rc != 0:
        add(FAIL, "HISTORY_LEAKS", "无法枚举 git 历史")
        return
    rev_list = [line for line in revs.splitlines() if line.strip()]
    if not rev_list:
        add(FAIL, "HISTORY_LEAKS", "历史 rev 数为 0，不能判绿")
        return

    # 阳性对照：仓库名必然出现在历史中；若为 0，说明扫描通道没工作。
    rc, control = git(repo, "grep", "-l", "-e", "chartaudit", rev_list[0], "--")
    if rc != 0 or not control.strip():
        add(FAIL, "HISTORY_LEAKS", "阳性对照失败：git grep 在 HEAD 未命中 chartaudit")
        return

    patterns = [
        ("绝对路径", r"(?<![A-Za-z0-9])[A-Za-z]:[\\/](?:Users|ProgramData|Documents and Settings)[\\/]"),
        ("MSYS 路径", r"(?<![A-Za-z0-9])/[A-Za-z]/(?:Users|ProgramData|home)/"),
    ]
    scanner_files = ("scripts/check_release.py", "plan/M6-desensitize-scan.md")
    hits = []
    revs_scanned = 0
    for rev in rev_list:
        revs_scanned += 1
        for label, pattern in patterns:
            rc, out = git(repo, "grep", "-n", "-e", pattern, rev, "--")
            if rc == 0 and out.strip():
                hits.append("%s:%s" % (label, rev[:8]))
        # 工作区标记：排除扫描器与脱敏留档自身的模式行（自引用豁免）
        rc, out = git(repo, "grep", "-l", "-e", "ProgramData[\\/]zcode", rev, "--")
        if rc == 0 and out.strip():
            leaked = [line for line in out.splitlines()
                      if line.split(":", 1)[-1] not in scanner_files]
            if leaked:
                hits.append("工作区标记:%s" % rev[:8])
    if hits:
        add(FAIL, "HISTORY_LEAKS",
            "全历史命中本机路径标记（词面不回显）：%s" % ", ".join(sorted(set(hits))[:6]))
    else:
        add(PASS, "HISTORY_LEAKS",
            "全历史 %d 个 rev 的 0 命中（阳性对照 chartaudit 命中，通道有效）" % revs_scanned)


def check_junk(repo):
    files = _tracked_files(repo)
    bad = []
    for rel in files:
        base = os.path.basename(rel)
        if ("__pycache__" in rel or base.endswith(".pyc") or base.startswith("=")
                or base in ("nul", ".DS_Store", "Thumbs.db")
                or rel.startswith(("out/", "dist/", ".pytest_cache/"))
                or rel.endswith((".egg-info", ".log"))):
            bad.append(rel)
    if bad:
        add(FAIL, "TRACKED_JUNK", "误入库垃圾/运行产物：%s" % ", ".join(bad[:6]))
    else:
        add(PASS, "TRACKED_JUNK", "入库文件无运行产物/字节码/日志垃圾（%d 个文件）" % len(files))


# ---------------------------------------------------------------- 在线面

def gh_ready():
    if not shutil.which("gh"):
        return False, "gh 不在 PATH"
    rc, out = run(["gh", "auth", "status"])
    if rc != 0:
        return False, "gh 未登录：%s" % out[:120]
    return True, ""


def repo_slug(repo, explicit):
    if explicit:
        return explicit
    env = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if env:
        return env
    rc, out = run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], cwd=repo)
    if rc == 0 and out.strip():
        return out.strip()
    return REPO_DEFAULT


def gh_json(args, repo):
    rc, out = run(["gh"] + args, cwd=repo)
    if rc != 0:
        return None, out[:200]
    try:
        return json.loads(out), ""
    except ValueError:
        return None, "gh 返回非 JSON：%s" % out[:120]


def check_online_repo(repo, slug):
    data, err = gh_json(["repo", "view", slug, "--json",
                         "nameWithOwner,visibility,url,description,repositoryTopics"], repo)
    if data is None:
        add(FAIL, "REPO_ONLINE", "无法读取 GitHub 仓库 %s：%s" % (slug, err))
        return
    if str(data.get("visibility", "")).upper() == "PUBLIC":
        add(PASS, "REPO_ONLINE", "公开仓库可达：%s" % data.get("url", slug))
    else:
        add(FAIL, "REPO_ONLINE", "仓库可见性不是 PUBLIC：%s" % data.get("visibility"))
    desc = (data.get("description") or "").strip()
    if desc:
        add(PASS, "REPO_DESCRIPTION", "仓库 description 非空")
    else:
        add(WARN, "REPO_DESCRIPTION", "仓库 description 为空")
    topics = data.get("repositoryTopics") or []
    names = []
    for item in topics:
        if isinstance(item, dict):
            names.append(item.get("name", ""))
        else:
            names.append(str(item))
    names = [name for name in names if name]
    if len(names) >= 3:
        add(PASS, "REPO_TOPICS", "topics 已设置（%d 个）" % len(names))
    elif names:
        add(WARN, "REPO_TOPICS", "topics 只有 %d 个（建议 >=3）" % len(names))
    else:
        add(WARN, "REPO_TOPICS", "topics 为空（DoD：topics 清零或留档）")


def check_remote_tag(repo, slug, tag):
    local = tag_commit(repo, tag)
    if not local:
        add(FAIL, "REMOTE_TAG", "本地 tag %s 不存在，无法对账" % tag)
        return
    rc, out = git(repo, "ls-remote", "--tags", "origin")
    remote = {}
    if rc == 0:
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) == 2:
                remote[parts[1]] = parts[0]
    peeled = remote.get("refs/tags/%s^{}" % tag) or remote.get("refs/tags/%s" % tag)
    if not peeled:
        # origin 不可用或未 fetch 到 tag：退回 gh api
        data, err = gh_json(["api", "repos/%s/git/ref/tags/%s" % (slug, tag)], repo)
        if data is None:
            add(FAIL, "REMOTE_TAG", "远端不存在 tag %s（%s）" % (tag, err))
            return
        obj = data.get("object") or {}
        peeled = obj.get("sha", "")
        if obj.get("type") == "tag":
            tag_data, _ = gh_json(["api", "repos/%s/git/tags/%s" % (slug, peeled)], repo)
            if tag_data:
                peeled = (tag_data.get("object") or {}).get("sha", peeled)
    if peeled == local:
        add(PASS, "REMOTE_TAG", "远端 tag 与本地同源（%s）" % local[:8])
    else:
        add(FAIL, "REMOTE_TAG", "远端 tag %s ≠ 本地 %s" % ((peeled or "缺")[:8], local[:8]))


def check_release(repo, slug, tag):
    data, err = gh_json(["release", "view", tag, "--repo", slug, "--json",
                         "tagName,isDraft,isPrerelease,url,assets,body"], repo)
    if data is None:
        add(FAIL, "RELEASE_EXISTS", "不存在 tag=%s 的 GitHub Release：%s" % (tag, err))
        return
    if data.get("isDraft"):
        add(FAIL, "RELEASE_EXISTS", "Release 仍是 draft")
    else:
        add(PASS, "RELEASE_EXISTS",
            "Release 存在（draft=%s，prerelease=%s）"
            % (data.get("isDraft"), data.get("isPrerelease")))
    assets = data.get("assets") or []
    names = [asset.get("name", "") for asset in assets]
    if not names:
        add(FAIL, "RELEASE_ASSETS", "Release 无附件（源码 zipball 不算产物）")
        return
    if ATTACHMENT not in names:
        add(FAIL, "RELEASE_ASSETS",
            "Release 附件缺 %s（现有：%s）" % (ATTACHMENT, ", ".join(names[:6])))
    else:
        add(PASS, "RELEASE_ASSETS", "Release 附件含 %s（共 %d 个）" % (ATTACHMENT, len(names)))

    local_path = os.path.join(repo, LOCAL_RELEASE_DIR, ATTACHMENT)
    local_hash = sha256_file(local_path) if os.path.isfile(local_path) else ""
    asset = next((item for item in assets if item.get("name") == ATTACHMENT), None)
    if asset:
        digest = str(asset.get("digest") or "")
        if digest.lower().startswith("sha256:"):
            if local_hash and digest.split(":", 1)[1].lower() == local_hash:
                add(PASS, "RELEASE_ASSET_DIGEST", "GitHub 资产 digest 与本地 sha256 一致")
            else:
                add(FAIL, "RELEASE_ASSET_DIGEST", "GitHub 资产 digest 与本地 sha256 不一致")
        else:
            add(WARN, "RELEASE_ASSET_DIGEST", "GitHub 未返回资产 digest，改用回下载校验")
        size = asset.get("size")
        if size is not None and os.path.isfile(local_path) and size != os.path.getsize(local_path):
            add(FAIL, "RELEASE_ASSET_SIZE", "Release 资产大小与本地副本不一致")
        elif size is not None:
            add(PASS, "RELEASE_ASSET_SIZE", "Release 资产大小与本地副本一致")

    if local_hash:
        with tempfile.TemporaryDirectory(prefix="chartaudit-release-") as tmp:
            rc, out = run(["gh", "release", "download", tag, "--repo", slug,
                           "--pattern", ATTACHMENT, "--dir", tmp], cwd=repo)
            downloaded = os.path.join(tmp, ATTACHMENT)
            if rc != 0 or not os.path.isfile(downloaded):
                add(FAIL, "RELEASE_DOWNLOAD", "附件回下载失败：%s" % out[:120])
            else:
                got = sha256_file(downloaded)
                if got == local_hash:
                    add(PASS, "RELEASE_DOWNLOAD", "附件回下载 sha256 与本地副本逐位一致")
                else:
                    add(FAIL, "RELEASE_DOWNLOAD", "回下载 sha256 ≠ 本地副本")


def ci_matrix_expectation(repo):
    """从 .github/workflows/ci.yml 现读矩阵口径（不在脚本里复制第二份版本清单）。

    返回 [(os, python), ...]；解析失败返回 []，由调用方判 FAIL —— 宁可红也不猜。
    """
    text = read_text(os.path.join(repo, ".github", "workflows", "ci.yml"))
    if not text:
        return []
    os_line = re.search(r"^\s*os:\s*\[([^\]]*)\]", text, re.M)
    py_line = re.search(r"^\s*python-version:\s*\[([^\]]*)\]", text, re.M)
    if not os_line or not py_line:
        return []
    split = lambda block: [part.strip().strip("\"'") for part in block.split(",") if part.strip()]
    os_list = split(os_line.group(1))
    py_list = split(py_line.group(1))
    return [(os_name, py) for os_name in os_list for py in py_list]


def _matrix_jobs(jobs, expected):
    combos = {}
    for job in jobs:
        name = job.get("name", "")
        conclusion = job.get("conclusion")
        status = job.get("status")
        key = None
        for os_name, py in expected:
            if os_name in name and py in name:
                key = (os_name, py)
        if key:
            combos[key] = (status, conclusion, name)
    return combos


def check_ci(repo, slug, tag):
    rc, out = run(["gh", "run", "list", "--repo", slug, "--workflow", "ci.yml",
                   "--limit", "100", "--json",
                   "databaseId,headSha,event,status,conclusion,headBranch,createdAt"], cwd=repo)
    if rc != 0:
        add(FAIL, "CI_RUNS", "无法读取 CI runs：%s" % out[:160])
        return
    try:
        runs = json.loads(out)
    except ValueError:
        add(FAIL, "CI_RUNS", "CI runs 返回非 JSON")
        return
    push_runs = [item for item in runs if item.get("event") == "push"]
    if not push_runs:
        add(FAIL, "CI_RUNS", "没有 event=push 的 workflow run")
        return
    add(PASS, "CI_RUNS", "push 触发的 workflow run 共 %d 个" % len(push_runs))

    head = ""
    tag_sha = tag_commit(repo, tag)
    rc, head = git(repo, "rev-parse", "HEAD")
    head = head.strip() if rc == 0 else ""

    def run_jobs(run_id):
        data, _err = gh_json(["api", "repos/%s/actions/runs/%s/jobs" % (slug, run_id)], repo)
        if not data:
            return None
        return data.get("jobs") or []

    final_runs = [item for item in push_runs
                  if item.get("headSha") in (head, tag_sha)
                  and item.get("conclusion") not in (None, "", "skipped")]
    if not final_runs:
        add(FAIL, "CI_FINAL_RUN", "HEAD/tag 对应提交没有已完成的 push run")
        return
    expected = ci_matrix_expectation(repo)
    if not expected:
        add(FAIL, "CI_MATRIX", "无法从 .github/workflows/ci.yml 解析 os / python-version 矩阵")
        return
    for item in final_runs:
        run_id = item.get("databaseId")
        jobs = run_jobs(run_id)
        if jobs is None:
            add(FAIL, "CI_MATRIX", "无法读取 run %s 的 jobs" % run_id)
            continue
        combos = _matrix_jobs(jobs, expected)
        want = set(expected)
        missing = want - set(combos)
        bad = [key for key, value in combos.items()
               if value[0] != "completed" or value[1] != "success"]
        label = "run %s（%s/%s）" % (run_id, item.get("headBranch"), str(item.get("headSha"))[:8])
        if missing:
            add(FAIL, "CI_MATRIX", "%s 缺矩阵 job：%s" % (label, sorted(missing)))
        elif bad:
            add(FAIL, "CI_MATRIX", "%s 矩阵 job 未全绿：%s" % (label, bad))
        else:
            add(PASS, "CI_MATRIX", "%s 四矩阵 job 全绿" % label)

    # 最终 HEAD 的 main push run 必须成功；tag push run 必须成功。
    def has_success(sha, branch):
        return any(item.get("headSha") == sha and item.get("conclusion") == "success"
                   and (branch is None or item.get("headBranch") == branch)
                   for item in push_runs)

    if head:
        if has_success(head, "main"):
            add(PASS, "CI_MAIN", "HEAD 的 main push run 成功")
        else:
            add(FAIL, "CI_MAIN", "HEAD 的 main push run 未成功（或尚未完成）")
    if tag_sha:
        if any(item.get("headSha") == tag_sha and item.get("conclusion") == "success"
               for item in push_runs):
            add(PASS, "CI_TAG", "tag 指向提交的 push run 成功")
        else:
            add(FAIL, "CI_TAG", "tag 指向提交的 push run 未成功")

    failed = [item for item in push_runs if item.get("conclusion") not in ("success",)]
    if failed:
        add(WARN, "CI_HISTORY",
            "存在非 success 的 push run（如实留档，不遮蔽）：%s"
            % ", ".join("%s:%s" % (item.get("databaseId"), item.get("conclusion")) for item in failed[:6]))
    else:
        add(PASS, "CI_HISTORY", "全部 push run 均为 success")

    # push 事件数 = run 数（GitHub Events API；新仓库事件面完整）
    data, err = gh_json(["api", "repos/%s/events?per_page=100" % slug], repo)
    if data is None:
        add(SKIP, "PUSH_RECON", "Events API 不可用：%s" % err)
        return
    events = [item for item in data if item.get("type") == "PushEvent"]
    if not events:
        add(SKIP, "PUSH_RECON", "Events API 返回 0 个 PushEvent（可能延迟），无法对账")
    elif len(events) == len(push_runs):
        add(PASS, "PUSH_RECON", "push 事件数 = push run 数（%d = %d）" % (len(events), len(push_runs)))
    else:
        add(WARN, "PUSH_RECON",
            "push 事件数 %d ≠ push run 数 %d（Events API 可能延迟；以 run 明细为准）"
            % (len(events), len(push_runs)))


# ---------------------------------------------------------------- 输出

def report(as_json):
    summary = {level: sum(1 for item in RESULTS if item["level"] == level)
               for level in (PASS, WARN, FAIL, SKIP)}
    if as_json:
        print(json.dumps({"results": RESULTS, "summary": summary}, ensure_ascii=False, indent=2))
    else:
        for item in RESULTS:
            print("[%s] %-22s %s" % (item["level"], item["code"], item["message"]))
        print("")
        print("汇总：PASS %d / WARN %d / FAIL %d / SKIP %d"
              % (summary[PASS], summary[WARN], summary[FAIL], summary[SKIP]))
    return 1 if summary[FAIL] else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="M6 发布终态自检（离线 + --online）")
    parser.add_argument("--repo", default="", help="仓库路径（默认当前目录）")
    parser.add_argument("--tag", default="", help="发布 tag（默认由 __init__.py 版本派生，如 v0.1.1）")
    parser.add_argument("--online", action="store_true", help="追加远端 / Release / CI 检查")
    parser.add_argument("--pre-tag", action="store_true", help="tag 前冒烟：跳过 tag 相关项")
    parser.add_argument("--slug", default="", help="GitHub 仓库 slug（默认自动解析）")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args(argv)

    RESULTS.clear()
    repo = os.path.abspath(args.repo or os.getcwd())
    if not check_repo(repo):
        return report(args.json)

    args.tag = resolve_release_names(repo, args.tag)
    if not args.tag:
        add(FAIL, "VERSION", "无法从 scripts/chartaudit/__init__.py 读取 __version__，无法派生 tag")
        return report(args.json)

    check_tag(repo, args.tag, args.pre_tag)
    check_post_tag(repo, args.tag, args.pre_tag)
    check_worktree(repo)
    check_version(repo)
    check_docs(repo)
    check_local_attachment(repo)
    check_commit_emails(repo)
    check_tagger_email(repo, args.tag, args.pre_tag)
    check_tracked_leaks(repo)
    check_history_leaks(repo)
    check_junk(repo)

    if args.online:
        ready, err = gh_ready()
        if not ready:
            add(FAIL, "GH_READY", err)
        else:
            slug = repo_slug(repo, args.slug)
            add(PASS, "GH_READY", "gh 已登录；仓库 slug=%s" % slug)
            check_online_repo(repo, slug)
            check_remote_tag(repo, slug, args.tag)
            check_release(repo, slug, args.tag)
            check_ci(repo, slug, args.tag)

    return report(args.json)


if __name__ == "__main__":
    sys.exit(main())
