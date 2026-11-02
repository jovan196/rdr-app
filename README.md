# RDR Studio — Aplikasi Ripple Down Rules berbasis Python GUI

Aplikasi desktop berbasis **Python Tkinter** untuk membantu pakar membuat sistem rekomendasi menggunakan metode Ripple Down Rules (RDR). Aplikasi menggunakan pustaka standar Python sehingga tidak memerlukan instalasi paket pihak ketiga.

## Fitur

- Knowledge base dimulai dari satu rule root dengan kondisi `t` (selalu benar) dan kesimpulan default yang dapat diubah.
- Konsultasi konsumen dengan formulir atribut dinamis.
- Mendukung atribut **numerik** dan **kategorikal**.
- Penelusuran binary tree: kondisi benar menuju **anak kanan / true-child**, kondisi salah menuju **anak kiri / false-child**.
- Pakar dapat menyetujui kesimpulan atau menolak dan membuat rule pengecualian.
- Kandidat kondisi pembeda dibuat otomatis dari kasus baru dan kasus kunci kesimpulan aktif:
  - Numerik: memakai titik tengah nilai kasus baru dan kasus kunci (`≥` atau `≤`).
  - Kategorikal: memakai kesamaan nilai kategori kasus baru (`=`).
- Kasus yang disetujui dapat menjadi kasus kunci jika rule tersebut belum memilikinya.
- Visualisasi pohon rule, detail rule, serta jejak inferensi.
- Knowledge base dapat disimpan/dibuka sebagai file JSON.
- Contoh domain rekomendasi laptop siap dicoba dan dapat diganti melalui tab Basis Pengetahuan.

## Cara menjalankan

Pastikan Python 3.9 atau lebih baru tersedia. Tkinter umumnya sudah disertakan pada distribusi Python desktop.

```bash
python rdr_app.py
```

Pada sebagian instalasi Linux, apabila Tkinter belum ada, pasang paket sistem `python3-tk` terlebih dahulu.

## Cara mencoba aplikasi

1. Jalankan aplikasi. Tab **Konsultasi** menampilkan contoh atribut rekomendasi laptop.
2. Isi semua atribut dan klik **Jalankan konsultasi**. Aplikasi menampilkan kesimpulan default dan jejak penelusuran.
3. Klik **Sesuai** untuk menyimpan kasus pertama sebagai kasus kunci kesimpulan default. Ini penting karena kasus kunci menjadi pembanding saat pakar membuat pengecualian.
4. Ubah satu atau beberapa atribut pada kasus berikutnya, lalu jalankan konsultasi.
5. Klik **Tidak sesuai — buat rule**. Pilih kondisi pembeda yang diusulkan aplikasi, masukkan kesimpulan pakar, lalu klik **Simpan rule pengecualian**.
6. Jalankan konsultasi ulang untuk menguji rule baru. Pohon dapat dilihat pada tab **Pohon Rule**.
7. Simpan knowledge base melalui menu **File → Simpan Sebagai…**.

## Cara kerja inferensi

Setiap node menyimpan kondisi, kesimpulan, kasus kunci, true-child, dan false-child. Jika kondisi node benar, kesimpulan node menjadi kesimpulan aktif dan inferensi mengikuti true-child. Jika kondisi node salah, kesimpulan aktif sebelumnya tetap berlaku dan inferensi mengikuti false-child. Penelusuran berhenti ketika cabang yang dipilih belum memiliki anak; kesimpulan aktif terakhir menjadi hasil sistem.

Ketika pakar menolak kesimpulan, aplikasi memilih node hasil (kesimpulan aktif) sebagai acuan kasus kunci. Kondisi pembeda yang diusulkan selalu diuji agar bernilai benar untuk kasus baru dan salah untuk kasus kunci. Rule baru ditempatkan pada cabang kosong yang ditempuh oleh kasus baru dari node frontier.

**Catatan metodologis:** rule default perlu memiliki satu kasus kunci yang disetujui pakar sebelum pengecualian pertama dapat dibuat. Ini mencegah aplikasi mengarang kasus pembanding yang belum divalidasi pakar.

## Pengujian mesin RDR

Jalankan unit test:

```bash
python -m unittest -v test_rdr.py
```

## Berkas

- `rdr_app.py` — aplikasi GUI dan mesin inferensi.
- `test_rdr.py` — unit test untuk inferensi, true/false branch, dan pembentukan kondisi pembeda.
- `contoh_knowledge_base.json` — contoh knowledge base yang dapat langsung dibuka di aplikasi.

## Pengumpulan tugas kelompok

Serahkan folder proyek ini dalam bentuk ZIP ke Edunex. Sesuai instruksi tugas, **wakil kelompok dengan NIM terbesar** yang melakukan submit. Pastikan `rdr_app.py`, `README.md`, `test_rdr.py`, dan `contoh_knowledge_base.json` ikut disertakan.
