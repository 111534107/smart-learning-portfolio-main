// 單次頁面內 Google Drive 選檔驗證；OAuth token 不寫入本機儲存或伺服器 session。
(() => {
  const preview = document.querySelector('.proposal-preview[data-drive-enabled="true"]');
  if (!preview) return;

  const button = document.getElementById("drive-connect");
  const feedback = document.getElementById("drive-feedback");
  const selectedPanel = document.getElementById("drive-selected");
  const fileName = document.getElementById("drive-file-name");
  const fileType = document.getElementById("drive-file-type");
  const fileLink = document.getElementById("drive-file-link");
  const clearButton = document.getElementById("drive-clear");
  const csrfToken = preview.dataset.csrfToken || "";
  const scope = "https://www.googleapis.com/auth/drive.file";
  let tokenClient = null;
  let accessToken = "";
  let pickerReady = Boolean(window.drivePreviewPickerReady);
  let identityReady = Boolean(window.drivePreviewIdentityReady);

  function announce(message, state = "") {
    feedback.textContent = message;
    feedback.dataset.state = state;
  }

  function updateButton() {
    if (!button) return;
    if (pickerReady && identityReady) {
      button.disabled = false;
      button.lastElementChild.textContent = "用 Google Drive 選一份檔案";
    }
  }

  function setupIdentity() {
    if (!identityReady || !window.google?.accounts?.oauth2 || tokenClient) return;
    tokenClient = window.google.accounts.oauth2.initTokenClient({
      client_id: preview.dataset.googleClientId,
      scope,
      callback: (response) => {
        if (response.error || !response.access_token) {
          announce("Google 授權未完成；你可以重新嘗試，或取消返回展示頁。", "error");
          button.disabled = false;
          button.lastElementChild.textContent = "重新連接 Google Drive";
          return;
        }
        accessToken = response.access_token;
        openPicker();
      },
      error_callback: () => {
        announce("Google 登入視窗未能開啟，請確認瀏覽器允許彈出視窗。", "error");
        button.disabled = false;
        button.lastElementChild.textContent = "重新連接 Google Drive";
      },
    });
  }

  function renderSelectedFile(file) {
    fileName.textContent = file.name;
    fileType.textContent = file.mimeType;
    if (file.webViewLink) {
      fileLink.href = file.webViewLink;
      fileLink.hidden = false;
    } else {
      fileLink.removeAttribute("href");
      fileLink.hidden = true;
    }
    selectedPanel.hidden = false;
    announce("已把這份原始檔連到展示成果。檔案仍留在你的 Google Drive。", "success");
  }

  async function verifySelectedFile(fileId) {
    announce("正在向 Google Drive 確認所選檔案…");
    const body = new URLSearchParams({
      csrf_token: csrfToken,
      file_id: fileId,
      access_token: accessToken,
    });
    const response = await fetch("/proposal-preview/drive-file", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
      body,
      credentials: "same-origin",
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "無法確認這份 Drive 檔案。");
    renderSelectedFile(result.file);
  }

  function openPicker() {
    if (!accessToken || !window.google?.picker) {
      announce("Google 選檔工具尚未載入，請重新整理頁面後再試。", "error");
      button.disabled = false;
      return;
    }
    const view = new window.google.picker.DocsView(window.google.picker.ViewId.DOCS)
      .setIncludeFolders(false)
      .setSelectFolderEnabled(false);
    const picker = new window.google.picker.PickerBuilder()
      .setAppId(preview.dataset.googleProjectNumber)
      .setOAuthToken(accessToken)
      .setDeveloperKey(preview.dataset.googlePickerApiKey)
      .addView(view)
      .setCallback((data) => {
        if (data.action === window.google.picker.Action.CANCEL) {
          announce("已取消選檔。你的檔案沒有變更。 ");
          button.disabled = false;
          return;
        }
        if (data.action !== window.google.picker.Action.PICKED) return;
        const picked = data.docs?.[0];
        if (!picked?.id) {
          announce("Google Picker 沒有回傳可用的檔案。", "error");
          button.disabled = false;
          return;
        }
        verifySelectedFile(picked.id).catch((error) => {
          announce(error.message || "無法確認這份 Drive 檔案。", "error");
        }).finally(() => {
          button.disabled = false;
          button.lastElementChild.textContent = "重新選取 Drive 檔案";
        });
      })
      .build();
    picker.setVisible(true);
  }

  button?.addEventListener("click", () => {
    setupIdentity();
    if (!tokenClient) {
      announce("Google 登入工具尚未載入，請確認網路後重新整理。", "error");
      return;
    }
    button.disabled = true;
    button.lastElementChild.textContent = "等待 Google 授權…";
    tokenClient.requestAccessToken({ prompt: accessToken ? "" : "consent" });
  });

  clearButton?.addEventListener("click", () => {
    selectedPanel.hidden = true;
    fileName.textContent = "";
    fileType.textContent = "";
    fileLink.removeAttribute("href");
    accessToken = "";
    announce("已清除此頁的選取狀態；Google 雲端檔案未變更。");
  });

  window.addEventListener("drive-preview-picker-ready", () => {
    pickerReady = true;
    updateButton();
  });
  window.addEventListener("drive-preview-identity-ready", () => {
    identityReady = true;
    setupIdentity();
    updateButton();
  });
  setupIdentity();
  updateButton();
})();
