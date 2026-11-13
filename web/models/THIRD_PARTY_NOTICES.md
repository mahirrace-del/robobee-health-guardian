# 3D anatomy model credits and licenses

## BodyParts3D skin

- Local asset: `anatomy-skin.glb`.
- Asset source: [human-body-simulator](https://github.com/yamz8/human-body-simulator), derived from BodyParts3D version 3.0.
- Original dataset: [BodyParts3D mirror](https://github.com/Kevin-Mattheus-Moerman/BodyParts3D) and [original archive](https://doi.org/10.18908/lsdba.nbdc00837-000).
- Attribution: BodyParts3D, © The Database Center for Life Science.
- License: [Creative Commons Attribution-ShareAlike 2.1 Japan](https://creativecommons.org/licenses/by-sa/2.1/jp/legalcode). The local license summary and legal code are in `LICENSE-BodyParts3D-CC-BY-SA-2.1-JP.txt` and `LEGALCODE-BodyParts3D.html`.
- Runtime changes: the asset is decoded, scaled and positioned in the anatomical viewport, then rendered with the app’s hologram material.

## Écorché anatomy layers

- Local asset: `ecorche.meshopt.glb`.
- Source: [Écorché](https://github.com/Charleeh/ecorche), based on BodyParts3D, © The Database Center for Life Science, and Z-Anatomy by Gauthier Kervyn.
- License: [Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/). The original attribution and license are in `ATTRIBUTION-Ecorche.md` and `LICENSE-Ecorche.md`.
- Runtime changes: the web-compressed model is scaled and positioned to fit the same viewport; meshes are tinted for the hologram and shown as the muscle or skeleton layer.

Redistributions of these identified assets or adaptations must preserve their respective attribution and license terms. These notices do not relicense unrelated project code.

## Runtime libraries

- Three.js and its GLTF/Draco loader add-ons: MIT; see `../vendor/THREE-LICENSE`.
- Draco decoder: Apache License 2.0; see `../vendor/DRACO-LICENSE.txt`.
- Meshoptimizer decoder: MIT; see `../vendor/MESHOPT-LICENSE.md`.
