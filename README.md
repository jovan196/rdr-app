# RDR Studio — Sistem Rekomendasi Pakar Berbasis Ripple Down Rules (RDR)

Aplikasi sistem rekomendasi AI berbasis **Ripple Down Rules (RDR)** menggunakan **Python** (antarmuka GUI **Tkinter** dan antarmuka **CLI**) untuk membantu pakar memberikan rekomendasi bagi konsumennya sekaligus membangun basis pengetahuan secara inkremental tanpa dependensi pustaka pihak ketiga.

## Kesesuaian dengan Spesifikasi Ripple Down Rules (RDR)

- **Rule awal default (`t → kesimpulan default`)**: Knowledge base berawal hanya dengan satu rule pada root (`R0`) yang kondisinya selalu benar (`t`), dengan kesimpulan default yang dapat diisi dan disesuaikan menurut domain masalah.
- **Penelusuran pohon biner (Binary Tree)**:
  - **Anak kanan (`true-child`)**: menggambarkan perkecualian dari node saat ini; dieksekusi ketika kondisi node **terpenuhi** (`True`), dan kesimpulan node tersebut menganulir kesimpulan aktif sebelumnya.
  - **Anak kiri (`false-child`)**: dieksekusi ketika kondisi node **tidak terpenuhi** (`False`), sambil mempertahankan kesimpulan aktif sebelumnya.
- **Kesimpulan akhir**: Sistem memberikan **kesimpulan terakhir yang diperoleh** sepanjang jalur penelusuran (karena kesimpulan sebelumnya telah dianulir oleh kesimpulan yang lebih baru).
- **Evaluasi pakar**:
  - **Jika pakar setuju**: rekomendasi tersebut diberikan kepada konsumen dan proses konsultasi selesai (jika rule aktif belum memiliki kasus kunci, kasus ini disimpan sebagai kasus kuncinya).
  - **Jika pakar tidak setuju**: sistem membuat rule perkecualian baru pada cabang berhentinya penelusuran (`true-child` atau `false-child`), dengan kesimpulan dari pakar dan kondisi yang dipilih dari kondisi yang **dipenuhi oleh kasus baru** serta **tidak dipenuhi oleh kasus kunci dari kesimpulan terakhir** yang dianulir.
  - Mendukung pemilihan **satu atau beberapa kondisi sekaligus (konjungsi `DAN`)** maupun penambahan **kondisi ambang kustom** yang divalidasi otomatis terhadap kasus baru dan kasus kunci.
  - Jika kasus pertama langsung ditolak saat `R0` belum memiliki kasus kunci spesifik, kasus kunci `R0` diperlakukan kosong sehingga pakar dapat langsung membuat rule perkecualian pertama tanpa terhambat.
- **Atribut numerik & kategorikal**: Mendukung atribut **numerik** (`=`, `≠`, `>`, `≥`, `<`, `≤`) dan **kategorikal** (`=`, `≠`, baik dengan pilihan kategori terdefinisi maupun teks bebas).
- **Visualisasi pohon biner 2D**: Tab **Pohon Biner RDR** menampilkan diagram visual pohon biner secara langsung (**Kiri = `false-child`**, **Kanan = `true-child`**) beserta sorotan jalur inferensi dan detail kasus kunci tiap rule.

## Arsitektur

Aplikasi dipisahkan secara bersih antara **inti mesin RDR** dan **antarmuka**:

- `rdr_core.py` — inti aplikasi murni tanpa dependensi antarmuka: mesin inferensi pohon biner, pembentukan kandidat pembeda & validasi kondisi kustom/konjungsi, validasi knowledge base, muat/simpan JSON, serta kelas `RDREngine`.
- `main.py` — antarmuka grafis (GUI) Tkinter beserta kanvas diagram pohon biner 2D.
- `cli.py` — antarmuka baris perintah (CLI) interaktif dengan fitur lengkap (konsultasi, evaluasi pakar, konfigurasi domain/kesimpulan default, kelola atribut, tampilan pohon biner, dan simpan/muat JSON).

## Cara Menjalankan

Pastikan Python 3.9 atau lebih baru tersedia.

### GUI (Tkinter)

```bash
python main.py
```

### CLI (Terminal)

```bash
python cli.py [knowledge_base.json]
```

## Cara Mencoba Aplikasi (GUI)

1. Jalankan `python main.py`. Secara bawaan sistem memuat contoh domain rekomendasi laptop yang hanya berisi satu rule awal `R0` (`t → kesimpulan default`). Untuk mengganti domain masalah atau membuat KB kosong dari awal, buka tab **Basis Pengetahuan** atau menu **File → Knowledge Base Baru (Kosong)**.
2. Pada tab **Konsultasi Konsumen**, isi nilai seluruh atribut konsumen lalu klik **Jalankan konsultasi**. Sistem menelusuri pohon biner dan menampilkan kesimpulan terakhir yang diperoleh beserta jejak penelusurannya.
3. Evaluasi oleh pakar:
   - Klik **✓ Pakar Setuju (Selesai)** apabila kesimpulan sudah tepat. Rekomendasi diberikan kepada konsumen dan proses selesai.
   - Klik **✗ Tidak Sesuai · Buat Rule Perkecualian** apabila kesimpulan belum tepat. Centang satu atau beberapa kondisi pembeda (atau tambahkan kondisi kustom), isi **Kesimpulan rekomendasi dari pakar**, lalu klik **Simpan Rule Perkecualian & Berikan Rekomendasi**.
4. Buka tab **Pohon Biner RDR** untuk melihat struktur visual **Anak Kiri (`false-child`)** dan **Anak Kanan (`true-child`)**, klik node mana pun untuk memeriksa kondisi, kesimpulan, dan kasus kuncinya.
5. Simpan knowledge base melalui menu **File → Simpan Sebagai…** (`Ctrl+S`).

## Pengujian Mesin RDR

Jalankan seluruh unit test:

```bash
python -m unittest -v test.py
```

## Daftar Berkas

- `rdr_core.py` — inti aplikasi (mesin inferensi RDR, validasi atribut numerik/kategorikal, kandidat kondisi pembeda, konjungsi `DAN`, dan alur update knowledge).
- `main.py` — antarmuka grafis (GUI) Tkinter beserta visualisasi diagram pohon biner.
- `cli.py` — antarmuka baris perintah (CLI).
- `test.py` — unit test untuk inferensi, pencabangan `true-child`/`false-child`, kasus kunci, kondisi konjungsi/kustom, dan serialisasi JSON.
- `knowledge_base.json` — contoh knowledge base awal (1 rule default `R0`) yang siap dibuka di aplikasi.
