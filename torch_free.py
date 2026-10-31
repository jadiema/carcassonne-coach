"""Lecture d'un state_dict PyTorch (.pt) sans PyTorch, et passe avant en NumPy."""
import pickle, zipfile, collections
import numpy as np

_DT = {"FloatStorage": np.float32, "DoubleStorage": np.float64, "LongStorage": np.int64,
       "IntStorage": np.int32, "HalfStorage": np.float16, "BoolStorage": np.bool_,
       "ByteStorage": np.uint8}

def load_state_dict(path):
    z = zipfile.ZipFile(path)
    root = z.namelist()[0].split("/")[0]
    class U(pickle.Unpickler):
        def find_class(self, mod, name):
            if mod == "torch._utils" and name == "_rebuild_tensor_v2":
                def rebuild(storage, offset, size, stride, *a):
                    if not size:
                        return storage[offset:offset + 1].reshape(())
                    return np.lib.stride_tricks.as_strided(
                        storage[offset:], shape=size,
                        strides=[s * storage.itemsize for s in stride]).copy()
                return rebuild
            if mod == "torch" and name in _DT:
                return name
            if mod == "collections" and name == "OrderedDict":
                return collections.OrderedDict
            if mod == "torch._utils" and name == "_rebuild_parameter":
                return lambda data, *a: data
            raise pickle.UnpicklingError(f"{mod}.{name}")
        def persistent_load(self, pid):
            _, stype, key, _loc, _n = pid
            raw = z.read(f"{root}/data/{key}")
            return np.frombuffer(raw, dtype=_DT[stype if isinstance(stype, str) else stype])
    return U(z.open(f"{root}/data.pkl")).load()

def conv2d(x, w, b, pad):
    """x (C,H,W), w (O,C,k,k) → (O,H,W) par im2col."""
    C, H, W = x.shape; O, _, k, _ = w.shape
    xp = np.pad(x, ((0, 0), (pad, pad), (pad, pad)))
    cols = np.lib.stride_tricks.sliding_window_view(xp, (k, k), axis=(1, 2))  # C,H,W,k,k
    cols = cols.transpose(1, 2, 0, 3, 4).reshape(H * W, C * k * k)
    return (cols @ w.reshape(O, -1).T + b).T.reshape(O, H, W)

def bn(x, sd, p, eps=1e-5):
    g, b = sd[p + ".weight"], sd[p + ".bias"]
    m, v = sd[p + ".running_mean"], sd[p + ".running_var"]
    return ((x - m[:, None, None]) / np.sqrt(v[:, None, None] + eps)) * g[:, None, None] + b[:, None, None]

relu = lambda x: np.maximum(x, 0)

def forward(sd, grid, scalars):
    """Même calcul que CarcassonneNet.forward (mode évaluation). Renvoie (value, policy)."""
    x = grid.astype(np.float32)
    for i in (1, 2, 3, 4):
        x = relu(bn(conv2d(x, sd[f"conv{i}.weight"], sd[f"conv{i}.bias"], 1), sd, f"bn{i}"))
    s = relu(sd["scalar_fc.weight"] @ scalars.astype(np.float32) + sd["scalar_fc.bias"])
    v = relu(bn(conv2d(x, sd["value_conv.weight"], sd["value_conv.bias"], 0), sd, "value_bn"))
    v = np.concatenate([v.mean(axis=(1, 2)), v.max(axis=(1, 2)), s])
    v = relu(sd["value_fc1.weight"] @ v + sd["value_fc1.bias"])
    value = float(1 / (1 + np.exp(-(sd["value_fc2.weight"] @ v + sd["value_fc2.bias"])[0])))
    p = relu(bn(conv2d(x, sd["policy_conv1.weight"], sd["policy_conv1.bias"], 1), sd, "policy_bn"))
    p = conv2d(p, sd["policy_conv2.weight"], sd["policy_conv2.bias"], 0).reshape(-1)
    mask = np.tile(grid[9].reshape(-1), p.size // grid[9].size)
    p = np.where(mask == 0, -np.inf, p)
    e = np.exp(p - p.max())
    return value, e / e.sum()
