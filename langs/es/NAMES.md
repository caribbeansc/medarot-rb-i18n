# Proper names: the canonical spelling

Always use the canonical form. The listed variants are wrong and should be fixed
wherever they turn up in a translation. Most of them are romanisations that drifted
apart while the text was being translated in bulk.

| Canonical | Variants NOT to use |
|---|---|
| **Gofu Bullet** | `Gofbullet`, `Gof Bullet`, `Gauf Bullet` |
| **Chibehemoth** | `Tibehemoth`, `Chibehemos` |
| **Titan Beetle** | `Titanbeetle` |
| **Hawk Dakar** | `Hawkdakar`, `Hawk Dacker` |
| **Frappé** | `Frappe` |
| **Wild Ucorn** | `Wild Ukon` |
| **Key Turtle** | `Keystartle` |
| **Warbandit** | `War Banit` |
| **Hanumonkey** | `Hanumankey` |
| **Arinsudayu** | `Arinsu Dayu` |
| **Under Tube** | `Undertube` |
| **Picopeco Hammer** | `Martillo Picopeco` |
| **Trampa Ganga** | `Trampa Yasu` |
| **Memorize** | `Memorizar` |
| **Remember** | `Recordar` |
| **Naturize** | `Naturalizar` |
| **Countract** | `Contrarrestar` |
| **Rompe Rocas** | `Embestida Rocosa` |
| **Atador** | `Sujeción` |
| **Sobremarcha** | `Overdrive` |
| **Reversión Total** | `Inversión Total` |
| **Restonación** | `Restnation` |
| **Bala Doble** | `Doble Bala` |
| **Sobreesfuerzo** | `Saturación` |
| **Conversión de Escudo** | `Conversión de escudo` |
| **Navi-Commune** | `Navi Commune` |
| **Shitori** | `Sitri` |

## Why some names stay in English

Card and part names that are recognisable English words, or model names of a
Medabot, are left as they are: the game itself treats them as brand names, and the
Latin American dub did the same. `Drive (Navi-Commune)` and `Drive (Particle)` are
model names, not descriptions.

## A warning about find-and-replace

Only replace a variant inside entries whose source text actually contains the
matching katakana. There are dangerous collisions: `Atadura` is the name of a
status effect in 21 entries **and** was also a stray variant of a part name whose
canonical form is `Atador`. A blind find-and-replace would rename the status
effect everywhere it appears.

`mrb extract` puts the source next to every translation, which is exactly what you
need to tell the two apart.
