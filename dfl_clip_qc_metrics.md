# DFL Clip QC – Optimale Metriken je Kriterium

Diese Datei fasst die 8 DFL-Anforderungen an Videoclips für LED-Banden zusammen.  
Für jedes Kriterium ist die optimale Metrik angegeben, die einen guten Kompromiss aus **Robustheit** und **Einfachheit in Python (OpenCV/NumPy)** bietet.  
Die Tabelle dient als Übersicht, die Erklärungen darunter geben Kontext. Sie ist so geschrieben, dass sowohl Menschen als auch LLMs sie gut verarbeiten können.

---

## Übersichtstabelle

| ID | Anforderung | Empfohlene Metrik | Warum diese Wahl? |
|----|-------------|-------------------|-------------------|
| **1** | Mindestlänge ≥ 15 s | Clip-Dauer = Frames ÷ FPS | Trivial über Video-Header; 100 % zuverlässig. |
| **2** | Lineare, gleichförmige Bewegung | Optical Flow Mittelvektor + Linearitätsprüfung (R²) | Mittelt Rauschen raus, prüft ob Bewegung einer geraden Linie folgt. |
| **3** | ≤ 2 Richtungswechsel/15 s | Dominante Bewegungsrichtung (Flow-Histogramm) → Wechsel zählen | Robust gegen Ausreißer; zählt nur stabile Wechsel. |
| **4** | Horizontale Geschwindigkeit ≤ 1.5 m/s | Optical Flow vₓ-Mittelwert → Umrechnung Pixel→Meter | Nutzt denselben Flow wie bei 2; einfache Skalierung auf reale Bande. |
| **5** | Harmonische Übergänge | Frame-zu-Frame ΔL_rel (Mittel-Luminanz) + Fade-Zeit ≥ 500 ms | Erkennt harte Cuts; Fade-Dauer verhindert Fehlalarme. |
| **6** | Keine Farbsprünge hell↔dunkel | ΔE (Lab, CIE76) pro Frame; 200 ms Fenster | Lab ist direkt in OpenCV; einfach und visuell nah an menschlicher Wahrnehmung. |
| **7** | Keine Blitze / Aufblinken | FFT der Luminanz-Zeitreihe (3–30 Hz) + Max ΔL_rel/Frame | Kombi erkennt periodisches Flicker + einzelne Blitze. |
| **8** | Keine ballähnl. Animationen | HoughCircles (Ballradius) + Bewegungsprüfung ≥ N Frames | OpenCV-Bordmittel; Bewegungscheck filtert statische Logos. |

---

## Erklärungen

### 1. Mindestlänge
- **Anforderung:** Jeder Clip muss mindestens 15 Sekunden lang sein.  
- **Metrik:** Dauer aus Frames ÷ FPS.  
- **Warum:** Direkt aus Metadaten, eindeutig überprüfbar.

### 2. Lineare, gleichförmige Bewegung
- **Anforderung:** Keine ruckartigen oder ungleichmäßigen Animationen.  
- **Metrik:** Optical Flow Mittelvektor pro Frame, Linearitätsprüfung über R².  
- **Warum:** Robust gegen Rauschen, prüft Bewegungen über Zeit.

### 3. Richtungswechsel
- **Anforderung:** Maximal 2 Wechsel in 15 Sekunden.  
- **Metrik:** Histogramm der Flow-Richtungen, dominante Richtung extrahieren, Wechsel zählen.  
- **Warum:** Störende Pingpong-Effekte werden so erkannt.

### 4. Geschwindigkeit
- **Anforderung:** Horizontal ≤ 1.5 m/s.  
- **Metrik:** Mittlerer Flow-vₓ, Umrechnung Pixel → Meter.  
- **Warum:** Einheitlich, robust, gleiche Basis wie bei 2.

### 5. Harmonische Übergänge
- **Anforderung:** Keine abrupten Schnitte.  
- **Metrik:** Frame-zu-Frame Luminanzänderung ΔL_rel, Fades ≥ 500 ms.  
- **Warum:** Einfache, aber zuverlässige Erkennung von harten Cuts.

### 6. Farbsprünge
- **Anforderung:** Keine abrupten Wechsel von hell ↔ dunkel.  
- **Metrik:** ΔE (CIE76, Lab) zwischen Frames, geprüft über 200 ms Fenster.  
- **Warum:** Farbmetrisch nahe am menschlichen Sehen, OpenCV unterstützt Lab direkt.

### 7. Blitze / Flicker
- **Anforderung:** Keine Blitze oder starkes Aufblinken.  
- **Metrik:** FFT der Luminanz-Zeitreihe (3–30 Hz) für Flicker + max ΔL_rel/Frame für Einzelblitze.  
- **Warum:** Kombination deckt sowohl periodisches als auch spontanes Flackern ab.

### 8. Ball-Animationen
- **Anforderung:** Keine rollenden, springenden oder fallenden Bälle in Ballgröße.  
- **Metrik:** Kreisdetektion mit HoughCircles im Ballradius-Bereich; nur zählen, wenn Bewegung ≥ N Frames.  
- **Warum:** OpenCV-Standardmethode, Bewegungsprüfung filtert statische Logos.

---
