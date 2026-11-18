# -*- coding: utf-8 -*-
import os, json, base64, urllib.request, urllib.error, urllib.parse, threading, tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from pathlib import Path
from datetime import datetime

API="https://api.github.com"
EX_DIR={".git","__pycache__",".venv","venv","env","node_modules",".pytest_cache",".mypy_cache","build","dist","cache","tmp","temp"}
EX_FILE={".env",".env.local","token.txt","github_token.txt","credentials.json","secrets.json"}
EX_EXT={".pyc",".pyo",".log",".tmp",".bak",".swp"}
MAX=100*1024*1024
WARN=50*1024*1024

class GH:
    def __init__(self,t): self.t=t
    def req(self,m,p,d=None):
        u=p if p.startswith("https://") else API+p
        b=None if d is None else json.dumps(d).encode()
        q=urllib.request.Request(u,data=b,method=m)
        q.add_header("Accept","application/vnd.github+json")
        q.add_header("X-GitHub-Api-Version","2022-11-28")
        q.add_header("Authorization","Bearer "+self.t)
        if b is not None:q.add_header("Content-Type","application/json")
        try:
            with urllib.request.urlopen(q,timeout=90) as r:
                raw=r.read()
                return json.loads(raw.decode()) if raw else {}
        except urllib.error.HTTPError as e:
            try:
                x=json.loads(e.read().decode()); msg=x.get("message","")
            except Exception: msg=str(e)
            raise RuntimeError(f"GitHub API {e.code}: {msg}")
        except urllib.error.URLError as e: raise RuntimeError(f"Koneksi gagal: {e}")
    def repos(self):
        out=[]; page=1
        while True:
            a=self.req("GET",f"/user/repos?per_page=100&page={page}&sort=updated")
            out+=a
            if len(a)<100: return out
            page+=1
    def contents(self,o,r,p="",b=None):
        p=urllib.parse.quote(p.strip("/"),safe="/")
        u=f"/repos/{o}/{r}/contents"+(f"/{p}" if p else "")
        if b:u+="?ref="+urllib.parse.quote(b)
        return self.req("GET",u)
    def put(self,o,r,p,data,msg,sha=None,branch=None):
        d={"message":msg,"content":base64.b64encode(data).decode()}
        if sha:d["sha"]=sha
        if branch:d["branch"]=branch
        p=urllib.parse.quote(p.strip("/"),safe="/")
        return self.req("PUT",f"/repos/{o}/{r}/contents/{p}",d)
    def delete(self,o,r,p,sha,branch):
        p=urllib.parse.quote(p.strip("/"),safe="/")
        return self.req("DELETE",f"/repos/{o}/{r}/contents/{p}",
                        {"message":"Delete "+p,"sha":sha,"branch":branch})
    def tree(self,o,r,b):
        ref=self.req("GET",f"/repos/{o}/{r}/git/ref/heads/{urllib.parse.quote(b,safe='')}")
        c=self.req("GET",f"/repos/{o}/{r}/git/commits/{ref['object']['sha']}")
        return self.req("GET",f"/repos/{o}/{r}/git/trees/{c['tree']['sha']}?recursive=1")

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("GitHub Transfer Tool V5")
        self.geometry("1050x700"); self.minsize(850,560)
        self.api=None; self.repos=[]; self.repo=None; self.branch="main"; self.path=""
        self.items=[]; self.history=[]; self.cfg=Path.home()/".github_transfer_v5.json"
        try:self.history=json.loads(self.cfg.read_text()).get("history",[])
        except Exception:pass
        self.ui()
    def ui(self):
        top=ttk.Frame(self,padding=8); top.pack(fill="x")
        ttk.Label(top,text="GitHub Personal Access Token:").pack(side="left")
        self.token=tk.StringVar(); ttk.Entry(top,textvariable=self.token,show="*",width=43).pack(side="left",padx=5)
        ttk.Button(top,text="Hubungkan / Refresh",command=self.connect).pack(side="left")
        self.user=ttk.Label(top,text="Belum terhubung"); self.user.pack(side="right")
        rf=ttk.LabelFrame(self,text="Repositori",padding=8); rf.pack(fill="x",padx=8,pady=5)
        self.rv=tk.StringVar(); self.combo=ttk.Combobox(rf,textvariable=self.rv,state="readonly",width=48)
        self.combo.pack(side="left",padx=5)
        ttk.Button(rf,text="Buka",command=self.open_repo).pack(side="left",padx=2)
        ttk.Button(rf,text="Buat Repo Baru",command=self.new_repo).pack(side="left",padx=2)
        ttk.Button(rf,text="Refresh Daftar",command=self.connect).pack(side="left",padx=2)
        bar=ttk.Frame(self,padding=8); bar.pack(fill="x")
        self.loc=ttk.Label(bar,text="Belum memilih repo"); self.loc.pack(side="left")
        ttk.Button(bar,text="Naik Folder",command=self.up).pack(side="right")
        mid=ttk.Frame(self,padding=(8,0)); mid.pack(fill="both",expand=True)
        self.tv=ttk.Treeview(mid,columns=("kind","name","size","sha"),show="headings",selectmode="extended")
        for c,t,w in [("kind","Jenis",75),("name","Nama",400),("size","Ukuran",100),("sha","SHA",300)]:
            self.tv.heading(c,text=t); self.tv.column(c,width=w)
        sy=ttk.Scrollbar(mid,orient="vertical",command=self.tv.yview); self.tv.configure(yscrollcommand=sy.set)
        self.tv.pack(side="left",fill="both",expand=True); sy.pack(side="right",fill="y")
        self.tv.bind("<Double-1>",self.double)
        act=ttk.LabelFrame(self,text="Operasi",padding=7); act.pack(fill="x",padx=8,pady=7)
        for label,fn in [("Buat Folder",self.folder),("Upload File",self.upload_files),("Upload Folder",self.upload_folder),
                         ("Backup C:\\mandarin_app",self.backup),("Download Pilihan",self.download),("Hapus Pilihan",self.delete),("Riwayat",self.show_history)]:
            ttk.Button(act,text=label,command=fn).pack(side="left",padx=2)
        bot=ttk.Frame(self,padding=8); bot.pack(fill="x")
        self.statusv=tk.StringVar(value="Masukkan token GitHub untuk memulai.")
        ttk.Label(bot,textvariable=self.statusv).pack(side="left",fill="x",expand=True)
        self.pb=ttk.Progressbar(bot,length=180,mode="determinate"); self.pb.pack(side="right")
    def status(self,s): self.after(0,lambda:self.statusv.set(s))
    def bg(self,fn,done):
        def go():
            try:r=fn(); self.after(0,lambda:done(r))
            except Exception as e:self.after(0,lambda:messagebox.showerror("Kesalahan",str(e))); self.status("Operasi gagal.")
        threading.Thread(target=go,daemon=True).start()
    def log(self,a,d):
        self.history.append({"time":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"action":a,"detail":d})
        self.history=self.history[-300:]
        try:self.cfg.write_text(json.dumps({"history":self.history},indent=2),encoding="utf-8")
        except Exception:pass
    def connect(self):
        t=self.token.get().strip()
        if not t:messagebox.showwarning("Token","Masukkan token terlebih dahulu."); return
        self.status("Mengambil daftar repositori...")
        def work():
            api=GH(t); me=api.req("GET","/user"); return api,me,api.repos()
        def done(x):
            self.api,me,self.repos=x; self.user.config(text="Terhubung: "+me["login"])
            self.combo["values"]=[f'{r["full_name"]}  ({"Private" if r["private"] else "Public"})' for r in self.repos]
            self.status(f'{len(self.repos)} repositori ditemukan.')
        self.bg(work,done)
    def selected_repo(self):
        i=self.combo.current()
        return self.repos[i] if 0<=i<len(self.repos) else None
    def open_repo(self):
        r=self.selected_repo()
        if not r:messagebox.showinfo("Repo","Pilih repo terlebih dahulu."); return
        self.repo=r["full_name"]; self.branch=r.get("default_branch") or "main"; self.path=""; self.refresh()
    def readonly(self):return bool(self.repo and self.repo.split("/")[-1].lower()=="karakter_mirip_p3")
    def writable(self):
        if not self.api or not self.repo:messagebox.showwarning("Belum siap","Hubungkan GitHub dan pilih repo."); return False
        if self.readonly():messagebox.showwarning("Hanya-baca","Karakter_Mirip_P3 dilindungi oleh aplikasi."); return False
        return True
    def refresh(self):
        if not self.repo:return
        o,r=self.repo.split("/",1); p=self.path; self.status("Memuat isi repo...")
        def work():
            try:
                x=self.api.contents(o,r,p,self.branch); return x if isinstance(x,list) else [x]
            except RuntimeError as e:
                if "404" in str(e):return []
                raise
        def done(items):
            self.items=items; self.tv.delete(*self.tv.get_children())
            for i,x in enumerate(items):
                size=x.get("size",0); self.tv.insert("","end",iid=str(i),values=("Folder" if x["type"]=="dir" else "File",x["name"],self.fmt(size),x.get("sha","")))
            self.loc.config(text=f"{self.repo}  |  {self.branch}  |  /{self.path}")
            self.status(f"{len(items)} item"+(" | Repo hanya-baca" if self.readonly() else ""))
        self.bg(work,done)
    def fmt(self,n):
        n=float(n or 0)
        for u in ["B","KB","MB","GB"]:
            if n<1024 or u=="GB":return f"{n:.1f} {u}"
            n/=1024
    def selected(self):
        return [self.items[int(i)] for i in self.tv.selection() if i.isdigit() and int(i)<len(self.items)]
    def double(self,e=None):
        a=self.selected()
        if not a:return
        x=a[0]
        if x["type"]=="dir":self.path="/".join(filter(None,[self.path,x["name"]])); self.refresh()
        else:self.download_one(x)
    def up(self):
        if self.path:self.path=self.path.rsplit("/",1)[0] if "/" in self.path else ""; self.refresh()
    def new_repo(self):
        if not self.api:messagebox.showwarning("Token","Hubungkan GitHub dulu.");return
        w=tk.Toplevel(self);w.title("Buat Repositori");w.transient(self);w.grab_set()
        f=ttk.Frame(w,padding=14);f.pack()
        ttk.Label(f,text="Nama repo:").grid(row=0,column=0,sticky="w")
        name=tk.StringVar();ttk.Entry(f,textvariable=name,width=36).grid(row=0,column=1,pady=4)
        ttk.Label(f,text="Deskripsi:").grid(row=1,column=0,sticky="w")
        desc=tk.StringVar();ttk.Entry(f,textvariable=desc,width=36).grid(row=1,column=1,pady=4)
        ttk.Label(f,text="Pilih privasi (wajib):").grid(row=2,column=0,sticky="w")
        privacy=tk.StringVar()
        ttk.Radiobutton(f,text="Private",variable=privacy,value="private").grid(row=2,column=1,sticky="w")
        ttk.Radiobutton(f,text="Public",variable=privacy,value="public").grid(row=3,column=1,sticky="w")
        def create():
            n=name.get().strip(); p=privacy.get()
            if not n or not p:messagebox.showwarning("Lengkapi","Nama dan pilihan privasi wajib diisi.",parent=w);return
            if "/" in n or " " in n:messagebox.showwarning("Nama","Nama repo tidak boleh mengandung spasi atau /.",parent=w);return
            if not messagebox.askyesno("Konfirmasi",f"Buat {n} sebagai {p.upper()}?",parent=w):return
            w.destroy()
            def work():return self.api.req("POST","/user/repos",{"name":n,"description":desc.get().strip(),"private":p=="private","auto_init":True})
            def done(r):
                self.log("Buat repo",r["full_name"]+" "+p.upper());messagebox.showinfo("Berhasil",r["html_url"]);self.connect()
            self.bg(work,done)
        ttk.Button(f,text="Buat Repo",command=create).grid(row=4,column=1,sticky="e",pady=9)
    def folder(self):
        if not self.writable():return
        n=simpledialog.askstring("Buat Folder","Nama folder:",parent=self)
        if not n:return
        n=n.strip().strip("/")
        if not n or "/" in n:messagebox.showwarning("Nama","Masukkan satu nama folder.");return
        o,r=self.repo.split("/",1);p="/".join(filter(None,[self.path,n,".gitkeep"]))
        def work():return self.api.put(o,r,p,b"",f"Create folder {n}",branch=self.branch)
        def done(_):self.log("Buat folder",p);self.refresh()
        self.bg(work,done)
    def scan(self,root):
        files=[];excluded=[]
        for p in root.rglob("*"):
            try:
                rel=p.relative_to(root)
                if any(x.lower() in EX_DIR for x in rel.parts):excluded.append((str(rel),"folder sementara/cache"));continue
                if p.is_file():
                    if p.name.lower() in EX_FILE or p.suffix.lower() in EX_EXT:excluded.append((str(rel),"file rahasia/sementara"));continue
                    if p.stat().st_size>MAX:excluded.append((str(rel),"lebih dari 100 MB"));continue
                    files.append(p)
            except OSError:excluded.append((str(p),"tidak dapat dibaca"))
        return files,excluded
    def upload_folder(self):
        if not self.writable():return
        s=filedialog.askdirectory(title="Pilih folder untuk diunggah sebagai satu folder")
        if s:self.preview(Path(s),include_root=True,action="Upload Folder")
    def backup(self):
        if not self.writable():return
        d=r"C:\mandarin_app"
        s=filedialog.askdirectory(title="Pilih folder sumber backup (isinya masuk langsung ke folder repo yang sedang dibuka)",initialdir=d if Path(d).exists() else str(Path.home()))
        if s:self.preview(Path(s),include_root=False,action="Backup")
    def preview(self,root,include_root=False,action="Upload"):
        files,excluded=self.scan(root);total=sum(p.stat().st_size for p in files)
        big=[p for p in files if p.stat().st_size>WARN]
        base="/".join(filter(None,[self.path,root.name if include_root else ""]))
        # Deteksi folder kosong agar struktur folder juga dapat dibuat di GitHub.
        empty_dirs=[]
        for d in [root]+[p for p in root.rglob("*") if p.is_dir()]:
            try:
                if not any(x.is_file() for x in d.rglob("*") if not any(z.lower() in EX_DIR for z in x.relative_to(root).parts)):
                    rel=d.relative_to(root).as_posix()
                    if d==root or rel not in {p.parent.relative_to(root).as_posix() for p in files}:
                        empty_dirs.append(rel)
            except OSError:pass
        destination=f"{self.repo}/{base}" if base else self.repo
        msg=(f"Sumber: {root}\nTujuan GitHub: {destination}\nFile upload: {len(files)}\n"
             f"Folder kosong: {len(empty_dirs)}\nUkuran total: {self.fmt(total)}\n"
             f"Dikecualikan: {len(excluded)}\nFile >50 MB: {len(big)}\n\n")
        if include_root:msg+="Nama folder sumber akan dibuat di GitHub, lalu seluruh isi dan subfoldernya dimasukkan ke dalamnya.\n"
        else:msg+="Isi folder sumber masuk langsung ke folder repo yang sedang dibuka (tanpa membuat folder sumber tambahan).\n"
        if big:msg+="\nFile besar:\n"+"\n".join(str(p.relative_to(root)) for p in big[:8])
        if excluded:msg+="\n\nContoh pengecualian:\n"+"\n".join(f"{p} ({why})" for p,why in excluded[:8])
        msg+="\n\nFolder .git, virtual environment, cache, file token/credential, file sementara, dan file >100 MB dikecualikan. Folder kosong akan diwakili file .gitkeep."
        if not files and not empty_dirs:messagebox.showinfo("Kosong",msg);return
        if messagebox.askyesno("Pratinjau upload",msg+"\n\nLanjutkan?"):
            self.upload_paths(files,root,destination_prefix=base,include_empty=empty_dirs)

    def upload_files(self):
        if not self.writable():return
        ps=filedialog.askopenfilenames(title="Pilih file")
        if ps:self.upload_paths([Path(x) for x in ps],None)
    def upload_paths(self,files,root,destination_prefix=None,include_empty=None):
        if not self.writable():return
        o,r=self.repo.split("/",1);pairs=[]
        prefix=self.path if destination_prefix is None else destination_prefix
        for p in files:
            rel=p.relative_to(root).as_posix() if root else p.name
            pairs.append((p,"/".join(filter(None,[prefix,rel]))))
        # Representasikan direktori kosong dengan .gitkeep (Git tidak menyimpan folder kosong).
        empty_pairs=[]
        for rel in (include_empty or []):
            marker=".gitkeep" if rel=="." else rel+"/.gitkeep"
            remote="/".join(filter(None,[prefix,marker]))
            empty_pairs.append((None,remote))
        pairs.extend(empty_pairs)
        if not pairs:messagebox.showinfo("Kosong","Tidak ada file atau folder yang dapat diunggah.");return
        self.status("Memeriksa file tujuan di GitHub...")
        self.pb["maximum"]=len(pairs);self.pb["value"]=0
        def work():
            tree=self.api.tree(o,r,self.branch).get("tree",[])
            remote_map={n.get("path"):n for n in tree if n.get("type")=="blob"}
            conflicts=[remote for _,remote in pairs if remote in remote_map]
            return conflicts,remote_map
        def checked(result):
            conflicts,remote_map=result
            if conflicts:
                preview="\n".join(conflicts[:12])
                more=f"\n... dan {len(conflicts)-12} lainnya" if len(conflicts)>12 else ""
                if not messagebox.askyesno("Konfirmasi pembaruan file",f"Ditemukan {len(conflicts)} file dengan jalur yang sama.\n\nFile berikut akan diperbarui; file lain yang hanya ada di GitHub tidak akan dihapus:\n{preview}{more}\n\nLanjutkan memperbarui file yang sama?",parent=self):
                    self.status("Upload dibatalkan.");return
            if not messagebox.askyesno("Konfirmasi upload",f"Upload {len(pairs)} file/penanda folder ke {self.repo}/{prefix}?\n\nFile baru ditambahkan. File yang tidak bertabrakan tetap dipertahankan.",parent=self):
                self.status("Upload dibatalkan.");return
            def upload_work():
                ok=0;fails=[]
                for i,(local,remote) in enumerate(pairs,1):
                    try:
                        data=local.read_bytes() if local else b""
                        old=remote_map.get(remote);sha=old.get("sha") if old else None
                        self.api.put(o,r,remote,data,"Upload "+Path(remote).name,sha,self.branch);ok+=1
                    except Exception as e:fails.append(f"{remote}: {e}")
                    self.after(0,lambda v=i:self.pb.configure(value=v));self.status(f"Upload {i}/{len(pairs)} | berhasil {ok} | gagal {len(fails)}")
                return ok,fails
            def done(x):
                ok,fail=x;self.log("Upload Folder/Backup",f"{self.repo}/{prefix}: {ok} berhasil, {len(fail)} gagal");self.refresh()
                messagebox.showinfo("Upload selesai",f"Berhasil: {ok}\nGagal: {len(fail)}"+("\n\n"+"\n".join(fail[:8]) if fail else ""))
            self.bg(upload_work,done)
        self.bg(work,checked)
    def download_one(self,item):
        o,r=self.repo.split("/",1);p=item.get("path") or "/".join(filter(None,[self.path,item["name"]]))
        target=filedialog.asksaveasfilename(title="Simpan file",initialfile=item["name"])
        if not target:return
        def work():
            x=self.api.contents(o,r,p,self.branch)
            if x.get("size",0)>MAX:raise RuntimeError("File lebih dari 100 MB.")
            Path(target).write_bytes(base64.b64decode(x["content"]));return target
        def done(out):self.log("Download",p+" -> "+out);messagebox.showinfo("Selesai","File disimpan:\n"+out)
        self.bg(work,done)
    def download(self):
        a=self.selected()
        if len(a)!=1:messagebox.showinfo("Pilih item","Pilih tepat satu file atau folder.");return
        x=a[0]
        if x["type"]=="file":self.download_one(x);return
        dest=filedialog.askdirectory(title="Folder tujuan download")
        if not dest:return
        o,r=self.repo.split("/",1);prefix=x.get("path") or "/".join(filter(None,[self.path,x["name"]]))
        def work():
            nodes=self.api.tree(o,r,self.branch).get("tree",[])
            chosen=[n for n in nodes if n.get("type")=="blob" and n.get("path","").startswith(prefix+"/")]
            ok=0;errs=[]
            for n in chosen:
                try:
                    if n.get("size",0)>MAX:raise RuntimeError("lebih dari 100 MB")
                    z=self.api.contents(o,r,n["path"],self.branch)
                    out=Path(dest)/Path(n["path"]).relative_to(prefix);out.parent.mkdir(parents=True,exist_ok=True)
                    out.write_bytes(base64.b64decode(z["content"]));ok+=1
                except Exception as e:errs.append(n["path"]+": "+str(e))
            return ok,errs
        def done(x):
            ok,errs=x;self.log("Download folder",prefix+f" ({ok} file)")
            messagebox.showinfo("Download selesai",f"Berhasil: {ok}\nGagal/dilewati: {len(errs)}"+("\n"+"\n".join(errs[:5]) if errs else ""))
        self.bg(work,done)
    def delete(self):
        if not self.writable():return
        a=self.selected()
        if not a:messagebox.showinfo("Pilih file","Pilih file yang akan dihapus.");return
        if any(x["type"]!="file" for x in a):messagebox.showwarning("Folder","Pilih file saja; hapus isi folder terlebih dahulu.");return
        if not messagebox.askyesno("Konfirmasi hapus",f"Hapus {len(a)} file dari GitHub?"):return
        o,r=self.repo.split("/",1)
        def work():
            ok=0;err=[]
            for x in a:
                p=x.get("path") or "/".join(filter(None,[self.path,x["name"]]))
                try:self.api.delete(o,r,p,x["sha"],self.branch);ok+=1
                except Exception as e:err.append(p+": "+str(e))
            return ok,err
        def done(x):
            ok,err=x;self.log("Hapus",f"{self.repo}: {ok} file");self.refresh()
            messagebox.showinfo("Hasil",f"Berhasil: {ok}\nGagal: {len(err)}"+("\n"+"\n".join(err[:5]) if err else ""))
        self.bg(work,done)
    def show_history(self):
        w=tk.Toplevel(self);w.title("Riwayat Aktivitas");w.geometry("760x420")
        t=ttk.Treeview(w,columns=("time","act","detail"),show="headings")
        for c,h,wd in [("time","Waktu",150),("act","Aktivitas",130),("detail","Rincian",450)]:
            t.heading(c,text=h);t.column(c,width=wd)
        t.pack(fill="both",expand=True,padx=8,pady=8)
        for x in reversed(self.history):t.insert("","end",values=(x.get("time"),x.get("action"),x.get("detail")))

if __name__=="__main__":App().mainloop()
