import os, tempfile, json, sys
# 模拟冻结环境的 APPDATA
tmp = tempfile.mkdtemp(prefix="apptest_")
os.environ["APPDATA"] = tmp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import Settings

print("APPDATA =", tmp)
s = Settings()
print("default output_dir:", s.output_dir)
s.update({
    "output_dir": os.path.join(tmp, "我的文稿"),
    "asr_engine": "openai",
    "whisper_model": "large-v3",
    "theme": "dark",
    "concurrent_tasks": 4,
    "openai_api_key": "sk-test-123",
})
path = s._PATH
print("wrote to:", path)
print("exists after save:", os.path.exists(path))
with open(path, encoding="utf-8") as f:
    print("on-disk json:", f.read())

# 新建实例，模拟下次启动
s2 = Settings()
print("--- reload ---")
print("output_dir:", s2.output_dir)
print("asr_engine:", s2.asr_engine)
print("whisper_model:", s2.whisper_model)
print("theme:", s2.theme)
print("concurrent_tasks:", s2.concurrent_tasks)
print("openai_api_key:", s2.openai_api_key)
assert s2.output_dir == os.path.join(tmp, "我的文稿"), "output_dir not persisted!"
assert s2.asr_engine == "openai"
assert s2.theme == "dark"
print("ALL PERSIST OK")
