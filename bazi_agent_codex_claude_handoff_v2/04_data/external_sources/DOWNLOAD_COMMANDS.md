# 外部数据下载命令

推荐使用包内脚本：

```bash
python 04_data/external_sources/download_sources.py \
  --manifest 04_data/external_sources/source_manifest.json \
  --dest data/external
```

只下载评测集：

```bash
python 04_data/external_sources/download_sources.py \
  --manifest 04_data/external_sources/source_manifest.json \
  --dest data/external \
  --usage evaluation_only
```

只下载某个来源：

```bash
python 04_data/external_sources/download_sources.py \
  --manifest 04_data/external_sources/source_manifest.json \
  --dest data/external \
  --source-id HF-CZUO-BAZI-300
```

## Hugging Face 手工方式

```bash
python -m pip install huggingface_hub
python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='tellang/yeji-processed', repo_type='dataset', local_dir='data/external/quarantine/tellang__yeji-processed')"
```

把 `repo_id` 替换为清单中的其他数据集名称即可。

## GitHub 手工方式

```bash
git clone --depth 1 https://github.com/ChenJiangxi/BaziQA.git data/external/evaluation_only/BaziQA
git clone --depth 1 https://github.com/DestinyLinker/MingLi-Bench.git data/external/evaluation_only/MingLi-Bench
```

下载后必须运行：

```text
1. 生成 SHA-256；
2. 保存许可证；
3. 写入下载日期和 commit/revision；
4. 执行评测集污染扫描；
5. 非评测数据进入 quarantine，而不是 approved。
```
