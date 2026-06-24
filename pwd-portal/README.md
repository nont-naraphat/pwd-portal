# Bearhouse and Sunsu — ศูนย์รหัสผ่าน (AD Self-Service + Lark)

เว็บพอร์ทัลให้พนักงานตรวจสถานะและเปลี่ยนรหัสผ่าน Active Directory ด้วยตัวเอง
พร้อมแจ้งเตือนผ่าน Lark ก่อนรหัสหมดอายุ ต่อ AD ผ่าน **LDAPS** (เปลี่ยนรหัสได้จริง)

- Frontend: หน้าเว็บ (อยู่ใน `app/static/index.html`)
- Backend: FastAPI + `ldap3` (`app/ad.py`, `app/lark.py`, `app/scheduler.py`, `app/main.py`)
- Deploy: Docker / Portainer

---

## เตรียมฝั่ง AD ก่อน (ครั้งเดียว)

1. **เปิด LDAPS บน DC** (พอร์ต 636) — ติดตั้ง role AD CS หรือ import cert ที่ชื่อตรงกับ FQDN ของ DC
   ทดสอบด้วย `ldp.exe` ต่อ `dc01.bearhouse.sunsu.local:636` แบบ SSL ให้ผ่านก่อน
2. **สร้าง service account** `svc-pwdportal` ตั้งรหัสแข็งแรง + Password never expires
3. **มอบสิทธิ์จำกัด** — Delegate Control ที่ OU ผู้ใช้ ให้สิทธิ์ "Reset Password" + อ่าน/เขียน `pwdLastSet` (ห้ามเป็น Domain Admin)
4. **export ใบรับรอง CA สาธารณะ** ของโดเมนเป็น `certs/bearhouse-ca.crt` (ไฟล์นี้ไม่ใช่ความลับ คอมมิตได้)

---

## ตั้งค่า

```bash
cp .env.example .env
# แก้ค่าใน .env: AD_BIND_PASSWORD, LARK_APP_ID, LARK_APP_SECRET, PORTAL_URL ฯลฯ
# วางไฟล์ certs/bearhouse-ca.crt
```

ค่า `AD_IP=192.168.0.4` จะถูก map ให้คอนเทนเนอร์ resolve ชื่อ `AD_HOST` ไปที่ IP นี้
(ตรวจ cert ตามชื่อได้ตามปกติ) ถ้ายังไม่พร้อมเรื่อง cert ตอนทดสอบ ตั้ง `AD_TLS_VALIDATE=none` ชั่วคราว

---

## รันในเครื่อง (ทดสอบ)

```bash
docker compose up --build
# เปิด http://localhost:8080
```

---

## ขึ้น GitHub

```bash
git init
git add .
git commit -m "init pwd portal"
git branch -M main
git remote add origin https://github.com/<org-หรือ-user>/pwd-portal.git
git push -u origin main
```

> ไฟล์ `.env` ถูก gitignore ไว้แล้ว — ความลับจะไม่ขึ้น GitHub

---

## Deploy ลง Portainer

มี 2 แบบ เลือกแบบ A (ง่ายสุด ไม่ต้องใช้ registry)

### แบบ A — Portainer build จาก Git โดยตรง (แนะนำ)
1. Portainer → **Stacks** → **Add stack** → ตั้งชื่อ `pwd-portal`
2. เลือก **Repository** → ใส่ URL repo + branch `main` + Compose path `docker-compose.yml`
3. เลื่อนลงส่วน **Environment variables** → ใส่ค่าทั้งหมดจาก `.env` (AD_HOST, AD_IP, AD_BASE_DN, AD_BIND_USER, AD_BIND_PASSWORD, LARK_APP_ID, LARK_APP_SECRET, PORTAL_URL ...)
4. (ตัวเลือก) เปิด **GitOps updates / auto update** ให้ดึง redeploy เองเมื่อ push ใหม่
5. กด **Deploy the stack** — Portainer จะ `build` จาก Dockerfile แล้วรันให้

> ใบรับรอง CA: เนื่องจาก compose mount `./certs` ตัวไฟล์ `certs/bearhouse-ca.crt` ที่คอมมิตไว้จะถูกดึงมาพร้อม repo อัตโนมัติ

### แบบ B — ใช้ image จาก GHCR (มี GitHub Actions ให้แล้ว)
1. push ขึ้น GitHub → workflow `build-image` จะ build แล้วดัน image ไป `ghcr.io/<repo>:latest`
2. ตั้ง package ให้ public หรือเพิ่ม Registry (GHCR) ใน Portainer ด้วย PAT
3. ใน `docker-compose.yml` เปลี่ยน `build: .` เป็น `image: ghcr.io/<repo>:latest`
4. Deploy stack ตามแบบ A

---

## ตรวจว่าใช้งานได้

- เปิดพอร์ทัล → เช็ก `GET /api/health` ควรได้ `{"ok":true,"ad":true,"lark":true}`
- login ด้วยบัญชี AD จริง → เห็นสถานะวันหมดอายุ
- ลองเปลี่ยนรหัส → เช็กว่า login ระบบอื่นด้วยรหัสใหม่ได้
- ทดสอบ Lark: `POST /api/notify/test` body `{"email":"คนใน_lark@..."}`

---

## หมายเหตุความปลอดภัย

- ใส่ TLS หน้าเว็บเสมอ (เปิด service `proxy` ใน compose หรือใช้ reverse proxy ขององค์กร)
- service account ใช้สิทธิ์น้อยที่สุด, ความลับอยู่ใน env/secret ไม่อยู่ในโค้ด
- เคสรหัส "หมดอายุไปแล้ว" จะ bind ด้วยรหัสเดิมไม่ได้ — ต้องมี path ให้ service account รีเซ็ตหลังยืนยันตัวตนทางอื่น (เพิ่มภายหลัง)
