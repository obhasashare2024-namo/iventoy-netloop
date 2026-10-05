import socket, subprocess, time, os, sys, json
from PIL import Image

SERIAL_SOCK = '/tmp/ser_cos_b.sock'
QMP_SOCK = '/tmp/qmp_cos_b.sock'
SERIAL_LOG = '/mnt/2tbnvS/tmp/serial_cos_b.log'
RAW_DIR = '/mnt/2tbnvS/tmp/frames_raw_cos_b'
CLEAN_DIR = '/mnt/2tbnvS/tmp/frames_clean_cos_b'
MP4_OUT = '/mnt/2tbnvS/tmp/track_b_cos_142g_boot.mp4'

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(CLEAN_DIR, exist_ok=True)
os.system(f'rm -rf {RAW_DIR}/* {CLEAN_DIR}/* {SERIAL_SOCK} {QMP_SOCK} {SERIAL_LOG} {MP4_OUT}')

TFTP_DIR = '/mnt/2tbnvS/tmp/tftp'

qemu_cmd = [
    'qemu-system-x86_64',
    '-name', 'cos-netloop-test',
    '-m', '4096',
    '-smp', '4',
    '-accel', 'kvm',
    '-vga', 'virtio',
    '-display', 'none',
    '-drive', 'file=nbd://127.0.0.1:10811/vtoy,format=raw,if=virtio,readonly=on',
    '-netdev', f'user,id=n0,tftp={TFTP_DIR},bootfile=boot/grub/i386-pc/core.0',
    '-device', 'virtio-net-pci,netdev=n0,mac=52:54:00:12:34:56',
    '-boot', 'n',
    '-chardev', f'socket,id=char0,path={SERIAL_SOCK},server=on,wait=off,logfile={SERIAL_LOG},logappend=off',
    '-serial', 'chardev:char0',
    '-qmp', f'unix:{QMP_SOCK},server=on,wait=off'
]

print('[COS-B] Launching QEMU VM (142GB CachyOS NetLoop)...', flush=True)
proc = subprocess.Popen(qemu_cmd)

for _ in range(50):
    if os.path.exists(SERIAL_SOCK) and os.path.exists(QMP_SOCK):
        break
    time.sleep(0.1)

ser = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
ser.connect(SERIAL_SOCK)
ser.setblocking(False)

qmp = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
qmp.connect(QMP_SOCK)
qmp.recv(4096)
qmp.sendall(json.dumps({'execute': 'qmp_capabilities'}).encode() + b'\n')
qmp.recv(4096)

start_time = time.time()
frame_idx = 0

print('[COS-B] Recording boot process frames (80s)...', flush=True)

while time.time() - start_time < 80:
    # Read serial non-blocking
    try:
        data = ser.recv(4096)
        if data:
            sys.stdout.write(data.decode('latin1', errors='replace'))
            sys.stdout.flush()
    except BlockingIOError:
        pass

    # Capture frame via screendump
    ppm_path = f'{RAW_DIR}/frame_{frame_idx:05d}.ppm'
    try:
        qmp.sendall(json.dumps({'execute': 'screendump', 'arguments': {'filename': ppm_path}}).encode() + b'\n')
        qmp.recv(1024)
    except:
        pass

    frame_idx += 1
    time.sleep(0.5)

ser.close()
qmp.close()
proc.terminate()
try: proc.wait(timeout=3)
except: proc.kill()

print(f'[COS-B] Capture complete. Total frames: {frame_idx}. Uniform resizing...', flush=True)

TARGET_W, TARGET_H = 1280, 800
valid_count = 0

for i in range(frame_idx):
    src = f'{RAW_DIR}/frame_{i:05d}.ppm'
    dst = f'{CLEAN_DIR}/frame_{i:05d}.png'
    if not os.path.exists(src): continue
    try:
        im = Image.open(src).convert('RGB')
        w, h = im.size
        scale = min(TARGET_W / w, TARGET_H / h)
        nw, nh = int(w * scale), int(h * scale)
        rim = im.resize((nw, nh), Image.Resampling.NEAREST)
        
        canvas = Image.new('RGB', (TARGET_W, TARGET_H), (0, 0, 0))
        ox = (TARGET_W - nw) // 2
        oy = (TARGET_H - nh) // 2
        canvas.paste(rim, (ox, oy))
        canvas.save(dst, 'PNG')
        valid_count += 1
    except Exception as e:
        print(f'Error processing frame {i}: {e}')

print(f'[COS-B] Formatted {valid_count} frames. Encoding 15fps QuickTime-compatible MP4...', flush=True)

enc_cmd = [
    'ffmpeg', '-y',
    '-framerate', '15',
    '-i', f'{CLEAN_DIR}/frame_%05d.png',
    '-c:v', 'libx264',
    '-preset', 'fast',
    '-crf', '18',
    '-pix_fmt', 'yuv420p',
    '-profile:v', 'high',
    '-level', '3.1',
    '-movflags', '+faststart',
    MP4_OUT
]
subprocess.run(enc_cmd, check=True)
print(f'[COS-B] Output successfully created at: {MP4_OUT}', flush=True)

if valid_count > 0:
    subprocess.run(['cp', f'{CLEAN_DIR}/frame_{valid_count-1:05d}.png', '/mnt/2tbnvS/tmp/track_b_cos_last.png'], check=True)
    if valid_count > 12:
        subprocess.run(['cp', f'{CLEAN_DIR}/frame_00012.png', '/mnt/2tbnvS/tmp/track_b_cos_menu.png'], check=True)

