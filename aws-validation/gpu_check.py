import json
import os
import subprocess
import torch

assert torch.cuda.is_available(), 'CUDA GPU is unavailable'
device = torch.cuda.get_device_properties(0)
matrix = torch.ones((128, 128), device='cuda')
product = matrix @ matrix
torch.cuda.synchronize()
assert float(product[0, 0]) == 128.0
result = {
    'status': 'GPU_CHECK_OK',
    'gpu_name': device.name,
    'gpu_memory_bytes': device.total_memory,
    'torch_version': torch.__version__,
    'cuda_version': torch.version.cuda,
    'matrix_result': float(product[0, 0]),
    'nvidia_smi': subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'], text=True).strip(),
}
os.makedirs('/opt/ml/model', exist_ok=True)
with open('/opt/ml/model/gpu_check.json', 'w') as f:
    json.dump(result, f)
print(json.dumps(result), flush=True)
