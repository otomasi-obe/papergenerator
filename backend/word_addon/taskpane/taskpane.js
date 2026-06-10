(function () {
  "use strict";

  const API_URL = "https://ai.otomasi.app/v1/chat/completions";
  const API_KEY = "sk-ccfa926bc01cfa19-7wxcu8-b7f17c13";

  let chatHistory = [];
  let isStreaming = false;

  function $(id) {
    return document.getElementById(id);
  }

  Office.onReady(function (info) {
    if (info.host === Office.HostType.Word) {
      document.getElementById("app").style.display = "flex";
      init();
    }
  });

  function init() {
    $("btnSend").addEventListener("click", handleSend);
    $("userInput").addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    });
    $("userInput").addEventListener("input", autoResize);
    $("btnReadAll").addEventListener("click", readAllDocument);
    $("btnReadSel").addEventListener("click", readSelection);
    $("btnUpload").addEventListener("click", function () {
      $("fileInput").click();
    });
    $("fileInput").addEventListener("change", handleFileUpload);
  }

  function autoResize() {
    var ta = $("userInput");
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 120) + "px";
  }

  function handleSend() {
    var content = $("userInput").value.trim();
    if (!content || isStreaming) return;

    $("userInput").value = "";
    autoResize();
    hideWelcome();

    appendMessage("user", content);

    var model = $("modelSelector").value;
    sendMessage(content, model);
  }

  function appendMessage(role, content) {
    var container = $("chatContainer");
    var typingEl = $("typingIndicator");

    var msg = document.createElement("div");
    msg.className = "message " + role;

    var avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = role === "user" ? "You" : "V";

    var bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.textContent = content;

    if (role === "ai") {
      var actions = document.createElement("div");
      actions.className = "message-actions";

      var copyBtn = document.createElement("button");
      copyBtn.textContent = "Copy";
      copyBtn.addEventListener("click", function () {
        navigator.clipboard.writeText(bubble.textContent).then(function () {
          showToast("Copied to clipboard");
        });
      });
      actions.appendChild(copyBtn);

      var insertBtn = document.createElement("button");
      insertBtn.textContent = "Insert to Doc";
      insertBtn.addEventListener("click", function () {
        insertText(bubble.textContent);
        showToast("Text inserted into document");
      });
      actions.appendChild(insertBtn);

      msg.appendChild(avatar);
      var wrapper = document.createElement("div");
      wrapper.appendChild(bubble);
      wrapper.appendChild(actions);
      msg.appendChild(wrapper);
    } else {
      msg.appendChild(avatar);
      msg.appendChild(bubble);
    }

    container.insertBefore(msg, typingEl);
    scrollToBottom();

    return bubble;
  }

  function hideWelcome() {
    var el = $("welcomeMessage");
    if (el) el.style.display = "none";
  }

  function scrollToBottom() {
    var c = $("chatContainer");
    setTimeout(function () {
      c.scrollTop = c.scrollHeight;
    }, 50);
  }

  function showTyping() {
    $("typingIndicator").classList.add("active");
    scrollToBottom();
  }

  function hideTyping() {
    $("typingIndicator").classList.remove("active");
  }

  function showToast(msg, isError) {
    var t = $("toast");
    t.textContent = msg;
    t.className = "toast" + (isError ? " error" : "") + " show";
    setTimeout(function () {
      t.className = "toast";
    }, 3000);
  }

  function sendMessage(content, model) {
    var systemMsg = {
      role: "system",
      content:
        'You are VIOLA AI, an intelligent document assistant inside Microsoft Word. ' +
        'You can help users write, edit, and understand documents. ' +
        'To insert text into the document, respond with the instruction: [INSERT]followed by the text to insert[/INSERT]. ' +
        'To replace text in the document, respond with: [REPLACE]search: <old text> | replacement: <new text>[/REPLACE]. ' +
        'Be concise and helpful. Format responses in plain text (no markdown).'
    };

    var messages = [systemMsg].concat(chatHistory).concat([
      { role: "user", content: content }
    ]);

    chatHistory.push({ role: "user", content: content });

    isStreaming = true;
    $("btnSend").disabled = true;
    showTyping();

    var aiBubble = null;
    var aiContent = "";

    fetch(API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + API_KEY
      },
      body: JSON.stringify({
        model: model,
        messages: messages,
        stream: true
      })
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("API error: " + response.status);
        }
        hideTyping();
        aiBubble = appendMessage("ai", "");

        var reader = response.body.getReader();
        var decoder = new TextDecoder("utf-8");
        var buffer = "";

        function read() {
          return reader.read().then(function (result) {
            if (result.done) {
              finishStream(aiBubble, aiContent);
              return;
            }

            buffer += decoder.decode(result.value, { stream: true });
            var lines = buffer.split("\n");
            buffer = lines.pop();

            for (var i = 0; i < lines.length; i++) {
              var line = lines[i].trim();
              if (!line || line === "data: [DONE]") continue;
              if (!line.startsWith("data: ")) continue;

              try {
                var json = JSON.parse(line.substring(6));
                var delta = json.choices && json.choices[0] && json.choices[0].delta;
                if (delta && delta.content) {
                  aiContent += delta.content;
                  aiBubble.textContent = aiContent;
                  scrollToBottom();
                }
              } catch (e) {}
            }

            return read();
          });
        }

        return read();
      })
      .catch(function (err) {
        hideTyping();
        appendMessage("ai", "Error: " + err.message);
        showToast("Failed to get response", true);
      })
      .finally(function () {
        isStreaming = false;
        $("btnSend").disabled = false;
      });
  }

  function finishStream(bubble, content) {
    chatHistory.push({ role: "assistant", content: content });

    var insertMatch = content.match(/\[INSERT\]([\s\S]*?)\[\/INSERT\]/);
    if (insertMatch) {
      var textToInsert = insertMatch[1].trim();
      insertText(textToInsert).then(function () {
        showToast("Text inserted into document");
      });
    }

    var replaceMatch = content.match(
      /\[REPLACE\]search:\s*([\s\S]*?)\s*\|\s*replacement:\s*([\s\S]*?)\[\/REPLACE\]/
    );
    if (replaceMatch) {
      var searchText = replaceMatch[1].trim();
      var replacement = replaceMatch[2].trim();
      replaceText(searchText, replacement).then(function () {
        showToast("Text replaced in document");
      });
    }

    isStreaming = false;
    $("btnSend").disabled = false;
  }

  function readAllDocument() {
    return Word.run(function (context) {
      var body = context.document.body;
      body.load("text");
      return context.sync().then(function () {
        var text = body.text.trim();
        if (!text) {
          showToast("Document is empty", true);
          return;
        }
        var preview = text.length > 2000 ? text.substring(0, 2000) + "..." : text;
        var msg = "=== Document Content ===\n" + preview;
        appendMessage("user", "[Read Document]");
        sendMessage(
          "Here is the content of the current Word document:\n\n" + preview + "\n\nPlease help me with this document.",
          $("modelSelector").value
        );
        showToast("Document content sent to AI");
      });
    }).catch(function (error) {
      showToast("Error reading document: " + error.message, true);
    });
  }

  function readSelection() {
    return Word.run(function (context) {
      var range = context.document.getSelection();
      range.load("text");
      return context.sync().then(function () {
        var text = range.text.trim();
        if (!text) {
          showToast("No text selected", true);
          return;
        }
        appendMessage("user", "[Read Selection]\n" + text);
        sendMessage(
          "Here is the selected text from the Word document:\n\n" + text + "\n\nPlease help me with this selection.",
          $("modelSelector").value
        );
        showToast("Selection sent to AI");
      });
    }).catch(function (error) {
      showToast("Error reading selection: " + error.message, true);
    });
  }

  function insertText(text) {
    return Word.run(function (context) {
      var range = context.document.getSelection();
      range.insertText(text, Word.InsertLocation.replace);
      return context.sync();
    }).catch(function (error) {
      showToast("Error inserting text: " + error.message, true);
    });
  }

  function replaceText(searchText, replaceText) {
    return Word.run(function (context) {
      var body = context.document.body;
      var searchResults = body.search(searchText, { matchCase: false });
      searchResults.load("items");
      return context.sync().then(function () {
        if (searchResults.items.length === 0) {
          showToast("Text not found: " + searchText, true);
          return;
        }
        for (var i = 0; i < searchResults.items.length; i++) {
          searchResults.items[i].insertText(replaceText, Word.InsertLocation.replace);
        }
        return context.sync().then(function () {
          showToast("Replaced " + searchResults.items.length + " occurrence(s)");
        });
      });
    }).catch(function (error) {
      showToast("Error replacing text: " + error.message, true);
    });
  }

  function handleFileUpload(event) {
    var file = event.target.files[0];
    if (!file) return;

    var ext = file.name.split(".").pop().toLowerCase();
    $("fileInput").value = "";

    if (ext === "txt") {
      var reader = new FileReader();
      reader.onload = function (e) {
        var text = e.target.result;
        appendMessage("user", "[Uploaded: " + file.name + "]");
        sendMessage(
          "I uploaded a text file (" + file.name + "). Here is the content:\n\n" + text + "\n\nPlease help me with this content.",
          $("modelSelector").value
        );
        showToast("File content sent to AI");
      };
      reader.readAsText(file);
    } else if (ext === "pdf" || ext === "docx" || ext === "doc") {
      var fileReader = new FileReader();
      fileReader.onload = function (e) {
        var base64 = btoa(
          new Uint8Array(e.target.result).reduce(function (data, byte) {
            return data + String.fromCharCode(byte);
          }, "")
        );
        appendMessage("user", "[Uploaded: " + file.name + "]");
        sendMessage(
          "I uploaded a " + ext.toUpperCase() + " file named \"" + file.name + "\". " +
          "Please help me work with this file. If you can read the content, summarize it for me.",
          $("modelSelector").value
        );
        showToast("File uploaded and sent to AI");
      };
      fileReader.readAsArrayBuffer(file);
    } else {
      showToast("Unsupported file type", true);
    }
  }
})();
