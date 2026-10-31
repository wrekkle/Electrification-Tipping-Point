"""Validate and package the PDFs obtained for the literature survey."""
from pathlib import Path
import csv
import hashlib
import json
import sys
import zipfile

import download_papers as downloader

ROOT = Path(__file__).resolve().parent
PAPERS = json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))
STATUS = json.loads((ROOT / 'download_status.json').read_text(encoding='utf-8'))

VERSIONS = {
    'P01': '期刊论文的机构库副本，含机构库封面',
    'P02': '学术主页公开的期刊论文扫描副本',
    'P03': '作者主页公开的会议论文全文',
    'P04': 'arXiv公开稿，下载时所提供版本',
    'P08': '1999年Eurandom报告99050；不是2001年期刊排版版',
    'P09': '机构库公开的期刊版，含封面',
    'P10': 'arXiv公开稿，含附录',
    'P15': 'arXiv公开稿',
    'P16': 'arXiv v2，2026-10-08修订稿',
    'P17': 'arXiv公开稿',
    'P18': 'NSF公开存档的期刊版',
    'P19': 'arXiv公开稿',
    'P20': '作者主页公开稿，卷期仍为占位符',
    'P21': '作者主页公开的期刊版',
    'P22': '作者主页公开稿',
    'P23': 'arXiv公开稿',
    'P24': 'arXiv公开稿',
    'P25': '大学机构库公开全文，含机构库封面',
    'P26': '作者主页公开稿',
    'P27': '大学机构库公开作者稿',
    'P32': '研究项目官网提供的作者全文',
    'P33': 'arXiv公开稿，期刊格式',
}

WHY_MISSING = {
    'P05': '出版商下载返回403；尚未找到可获取的作者或机构库公开全文。',
    'P06': '出版商标注开放获取，但自动下载返回403/406；作者代码仓库未附论文全文。',
    'P07': '期刊归档与JSTOR返回网页，未取得有效PDF；作者主页仅指向归档入口。',
    'P11': 'SSRN自动访问返回403；尚未找到其他公开PDF。',
    'P12': 'SSRN自动访问返回403；作者主页仍指向SSRN。',
    'P13': 'SSRN自动访问返回403；作者主页仍指向SSRN。',
    'P14': 'ACM返回403，检索到的OpenReview链接返回网页；作者主页未提供另一份全文。',
    'P28': '出版商下载返回403；尚未找到可获取的作者或机构库公开全文。',
    'P29': 'SSRN自动访问返回403；检索到的Optimization Online候选链接已失效。',
    'P30': '期刊公开PDF链接发生连接/TLS错误；NTNU旧链接迁移后返回网页。',
    'P31': 'Sage自动下载返回403；Rosenheim机构库需要浏览器人机验证。',
    'P34': '出版商下载返回403；尚未取得这篇特定论文的作者全文，未用同作者其他论文替代。',
    'P35': '出版商与SSRN公开稿链接自动访问均返回403。',
}

MANUAL_URLS = {
    'P11': 'https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4320423',
    'P12': 'https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6384158',
    'P13': 'https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7109699',
    'P29': 'https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6254138',
    'P35': 'https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5219198',
}


def link(path, absolute):
    return (ROOT / path).as_posix() if absolute else Path(path).as_posix()


def make_index(absolute=False):
    downloaded = [p for p in PAPERS if STATUS[p['id']]['status'] == 'downloaded']
    missing = [p for p in PAPERS if STATUS[p['id']]['status'] != 'downloaded']
    megabytes = sum(STATUS[p['id']]['bytes'] for p in downloaded) / (1024 * 1024)
    lines = [
        '# 停车、充电与数学算法：论文下载目录', '',
        '整理日期：2026年10月29日。编号P01—P35与此前的文献清单一致。', '',
        f'已取得 **{len(downloaded)}/35篇有效PDF**，合计约 **{megabytes:.1f} MB**；另外{len(missing)}篇列在下方待补清单。', '',
        '所有已下载文件均检查了PDF文件头、可解析页数及前3页中的题名关键词，并记录SHA-256。此检查不等于已精读全文或证明了研究创新性。', '',
        '**版本提醒：**部分文件是作者稿或预印本。P08为同题同作者的1999年报告版，文献主条目对应2001年期刊论文，两者需区分；正式引用时应核对所用版本。页数包含机构库封面或附录。', '',
        '## 建议先打开的6篇', '',
    ]
    reasons = {
        'P09': '先看最接近问题的停车准入模型与阈值策略。',
        'P03': '理解怎样联合预测下一辆车的到达时间和类型。',
        'P10': '理解车位归还后的在线资源分配。',
        'P18': '理解预测误差怎样影响最后的优化决策。',
        'P19': '理解输入数据不可靠时的分布鲁棒优化。',
        'P16': '查看如何利用预测并对预测失误提供保底；理论难度较高。',
    }
    for pid, reason in reasons.items():
        paper = next(p for p in PAPERS if p['id'] == pid)
        file = Path('PDFs') / STATUS[pid]['filename']
        lines.append(f"- **{pid}** [{paper['title']}](<{link(file, absolute)}>)：{reason}")
    lines += ['', '## 已取得的全文', '']
    groups = list(dict.fromkeys(p['group'] for p in PAPERS))
    for group in groups:
        group_papers = [p for p in downloaded if p['group'] == group]
        if not group_papers:
            continue
        lines += [f'### {group}', '', '| 编号 | 题名与PDF | 页数 | 下载版本 |', '|---|---|---:|---|']
        for p in group_papers:
            pid = p['id']; record = STATUS[pid]
            file = Path('PDFs') / record['filename']
            lines.append(f"| {pid} | [{p['title']}](<{link(file, absolute)}>) | {record['pages']} | {record['version_note']} |")
        lines.append('')
    lines += ['## 尚未取得有效PDF的13篇', '',
              '下列项目没有计入已下载数量。403、人机验证或连接错误并不说明论文一定收费；可在普通浏览器或学校图书馆入口继续访问。每篇另附一个Windows网页快捷方式，位于“待补全文链接”文件夹。', '',
              '| 编号 | 论文原始入口 | 当前情况 |', '|---|---|---|']
    for p in missing:
        pid = p['id']
        lines.append(f"| {pid} | [{p['title']}]({MANUAL_URLS.get(pid, p['url'])}) | {WHY_MISSING[pid]} |")
    lines += ['', '## 其他文件', '',
              f"- [35篇中文文献注释与用途](<{link('literature_35.md', absolute)}>)。",
              f"- [研究路线与候选数学问题](<{link('research_framework.md', absolute)}>)。",
              f"- [完整下载清单CSV](<{link('download_manifest.csv', absolute)}>)：含书目、来源、版本、页数与校验值。", '',
              '预印本的下载日期或修订年份可能与正式发表年份不同。下载来源为公开期刊入口、作者主页、机构库或预印本平台；未用摘要页、幻灯片或不同论文替代缺失全文。', '']
    return '\n'.join(lines)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    hashes = set()
    rows = []
    shortcut_dir = ROOT / '待补全文链接'
    shortcut_dir.mkdir(exist_ok=True)
    for paper in PAPERS:
        pid = paper['id']; record = STATUS[pid]
        if record['status'] == 'downloaded':
            path = ROOT / 'PDFs' / record['filename']
            data = path.read_bytes()
            checked = downloader.inspect_pdf(data, paper)
            assert checked['text_verified'] and checked['title_keyword_coverage'] >= .55
            assert checked['sha256'] == record['sha256']
            assert checked['sha256'] not in hashes, f'Duplicate PDF: {pid}'
            hashes.add(checked['sha256'])
            record.update(checked)
            record['bytes'] = len(data)
            record['version_note'] = VERSIONS[pid]
        else:
            record['missing_note'] = WHY_MISSING[pid]
            url = MANUAL_URLS.get(pid, paper['url'])
            (shortcut_dir / f'{pid}_{downloader.filename(paper)[4:-4]}.url').write_text(
                '[InternetShortcut]\nURL=' + url + '\n', encoding='utf-8')
        rows.append({
            '编号': pid, '方向': paper['group'], '年份': paper['year'],
            '作者': paper['authors'], '题名': paper['title'], '刊物': paper['venue'],
            'DOI': paper.get('doi', ''),
            '状态': '已下载' if record['status'] == 'downloaded' else '未取得PDF',
            '版本或缺失原因': record.get('version_note', record.get('missing_note', '')),
            'PDF文件': 'PDFs/' + record['filename'] if record.get('filename') else '',
            '页数': record.get('pages', ''), '字节数': record.get('bytes', ''),
            '下载来源': record.get('source_url', ''),
            '论文入口': MANUAL_URLS.get(pid, paper['url']),
            'SHA256': record.get('sha256', ''),
        })
    (ROOT / 'download_status.json').write_text(json.dumps(STATUS, ensure_ascii=False, indent=2), encoding='utf-8')
    with (ROOT / 'download_manifest.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    (ROOT / '下载目录.md').write_text(make_index(True), encoding='utf-8')
    (ROOT / 'README.md').write_text(make_index(False), encoding='utf-8')
    progress = ROOT / 'progress.md'
    original = progress.read_text(encoding='utf-8').split('\n\n全文下载进度：')[0].rstrip()
    progress.write_text(original + '\n\n全文下载进度：已取得并校验22篇PDF；13篇因访问限制、连接问题或未找到公开全文而待补。P08为1999年报告版本。详见下载目录.md和download_manifest.csv。\n', encoding='utf-8')
    zip_path = ROOT / f'相关论文_已下载{len(hashes)}篇_20261029.zip'
    included = [ROOT / 'README.md', ROOT / 'literature_35.md', ROOT / 'research_framework.md',
                ROOT / 'sources.json', ROOT / 'download_manifest.csv']
    included += sorted((ROOT / 'PDFs').glob('*.pdf'))
    included += sorted(shortcut_dir.glob('*.url'))
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in included:
            archive.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.testzip() is None
        assert len([n for n in archive.namelist() if n.endswith('.pdf')]) == len(hashes)
    print(json.dumps({'validated_pdfs': len(hashes), 'missing': 35-len(hashes),
                      'zip': str(zip_path), 'zip_MB': round(zip_path.stat().st_size/1024/1024, 2),
                      'index': str(ROOT/'下载目录.md')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
