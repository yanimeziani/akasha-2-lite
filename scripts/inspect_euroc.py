import csv
import numpy as np

with open("data/euroc_v1_02_groundtruth.csv", "r") as f:
    reader = csv.reader(f)
    header = next(reader)
    rows = [list(map(float, row)) for row in reader if row]

data = np.array(rows)
print("Columns count:", len(header))
print("Total rows:", len(data))

t_ns = data[:, 0]
t_sec = (t_ns - t_ns[0]) * 1e-9
print(f"Flight Duration: {t_sec[-1]:.2f} seconds")
dt_mean = np.mean(np.diff(t_sec))
print(f"Mean dt: {dt_mean:.5f} seconds (~{1.0/dt_mean:.0f} Hz)")

pos = data[:, 1:4]
print(f"X range: [{pos[:, 0].min():.2f}, {pos[:, 0].max():.2f}] m")
print(f"Y range: [{pos[:, 1].min():.2f}, {pos[:, 1].max():.2f}] m")
print(f"Z range: [{pos[:, 2].min():.2f}, {pos[:, 2].max():.2f}] m")

