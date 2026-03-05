# PlaneToPBR — One-Click PBR Plane Generator for Blender

![PlaneToPBR Demo](assets/PlanetoPBR.gif)

PlaneToPBR is a free Blender extension that generates a **fully textured PBR plane from a single image in one click**.

The extension automatically generates and applies:

- Diffuse
- Normal
- Roughness
- Depth
- Prompt Bases Mask

This allows artists to quickly convert reference images into usable **3D textured geometry**.

---

# Installation

1. Open **Blender**
2. Go to **Edit → Preferences**

![Preferences](assets/extention.png)

3. Click **Get Extensions**
4. Open the dropdown menu and select **Install from Disk**

![Install from Disk](assets/installDisk.png)

5. Select the `PlaneToPBR.zip` file

![Select Zip](assets/installZip.png)

6. Enable the extension after installation.

---

# Using PlaneToPBR

After installing, open the **PlaneToPBR panel** in the 3D viewport sidebar.

![Panel Location](assets/panel.png)

---
# UI Location

The panel is located in the **3D viewport sidebar**.

![UI Location](assets/ui.png)

---


## Step 1 — Enter Prompt

Optionally enter a prompt to guide the AI segmentation.

![Prompt Field](assets/prompt.png)

Example:

```
Windows
```

---

## Step 2 — Select Image

Click the file browser button and select your source image.

![File Browser](assets/selectFile.png)

Then choose the image file.

![Select Image](assets/file.png)

---

## Step 3 — Generate PBR Plane

Click **Generate PBR Plane**.

![Generate Button](assets/generate.png)

The add-on will:

1. Send the image to the AI pipeline  
2. Generate PBR maps  
3. Create a correctly scaled plane  
4. Build the material automatically  

---

# Generated Shader

The extension automatically builds a full **PBR shader network**.

![Shader Graph](assets/shaders.png)

---

# Geometry Setup

For best depth results, adjust modifiers:

- Subdivision
- Displacement

Example settings:

![Modifier Settings](assets/modifier.png)

---


# Running Tests

Build the test container:

```
podman build --no-cache -t planetopbr-tests .
```

or

```
docker build --no-cache -t planetopbr-tests .
```

Run tests:

```
podman run --rm planetopbr-tests
```

or

```
docker run --rm planetopbr-tests
```

---

# License

MIT License

---

## AI Models

PlaneToPBR relies on several open-source AI models:

| Model | Purpose | Repository |
|------|------|------|
| **CLIPSeg** | Text-guided segmentation (mask generation) | https://github.com/timojl/clipseg |
| **DeepBump** | Normal & roughness map generation | https://github.com/HugoTini/DeepBump |
| **MiDaS** | Depth estimation | https://github.com/isl-org/MiDaS |
