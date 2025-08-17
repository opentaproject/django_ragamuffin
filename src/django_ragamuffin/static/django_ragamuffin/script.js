const script = document.createElement("script");
script.src = "https://code.jquery.com/jquery-3.6.0.min.js";
document.head.appendChild(script);

function getCookie(name) {
  const cookieString = document.cookie;
  const cookies = cookieString.split(";");
  for (let cookie of cookies) {
    cookie = cookie.trim();
    if (cookie.startsWith(name + "=")) {
      return cookie.substring(name.length + 1);
    }
  }
  return null;
}

document.addEventListener("DOMContentLoaded", function () {
  // Your code here will run after the DOM is fully loaded

  document.getElementById("submitBtn").addEventListener("click", function () {
    document.cookie = "busy=true; max-age=3600; path=/";
    let count = 0;
    const intervalId = setInterval(() => {
      const busy = getCookie("busy");
      count = count + 1;
      if (count > 80) {
        var patience =
          " be patient! It has 'only' been " +
          Math.floor(count / 5).toString() +
          " s";
      } else if (count > 40) {
        var patience = " be patient! Give it up to a 2 minutes !";
      } else if (count > 20) {
        var patience = " be patient!";
      } else {
        var patience = "";
      }
      var btn = document.getElementById("submitBtn");
      if (busy == "true") {
        btn.type = "button";
        btn.textContent = "Wait ... " + patience;
        btn.style.backgroundColor = "darkorange";
        btn.style.color = "white"; // optional: for better contrast
      } else {
        btn.type = "submit";
        btn.textContent = "Submit ";
      }
    }, 200);
    setTimeout(() => {
      clearInterval(intervalId);
      console.log("Interval stopped");
    }, 60000);
  });

  console.log("Document is ready!");
});

function button_color(btn, color) {
  btn.disabled = color !== "green";
  btn.style.backgroundColor = color;
  btn.style.color = "white"; // optional: for better contrast
  return btn;
}

function handleClick(event) {
  // console.log("HANDLE_CLICK")
  event.preventDefault();
  document.getElementById("response-block").style.display = "block";
  var txt = event.currentTarget?.value || "";
  const textarea = document.getElementById("id_query");
  if (textarea) {
    textarea.value = txt;
  }
  var innerDiv = event.currentTarget?.querySelector(".innerDiv");
  var content = innerDiv?.innerHTML || "";
  var innerComment = event.currentTarget?.querySelector(".innerComment");
  var comment = innerComment?.innerHTML || "";
  const comment_area = document.getElementById("comment");
  if (comment_area) {
    comment_area.value = comment;
  }

  var innerChoice = event.currentTarget?.querySelector(".innerChoice");
  var choice = innerChoice ? String(innerChoice.innerHTML) : "";
  document.querySelectorAll('input[name="option"]').forEach(function (radio) {
    radio.checked = false;
  });
  const choiceInput = document.querySelector(
    `input[name="option"][value="${choice}"]`
  );
  if (choiceInput) {
    choiceInput.checked = true;
  }

  const response_area = document.getElementById("response");
  // console.log("TARGET = ", event.currentTarget)
  var buttons = document.getElementsByName("oldquery").forEach(button => {
  button.style.backgroundColor = "";
});
  
  event.currentTarget.style.backgroundColor = "lightblue"; 
  const message_index =
    event.currentTarget?.querySelector(".mindex")?.innerHTML || "";
  const mindexarea = document.getElementById("newmessage_index");
  if (mindexarea) {
    mindexarea.value = message_index;
  }
  if (response_area) {
    if ( message_index ){
    response_area.innerHTML = '<b  style="background-color: lightblue; padding: 4px " >Query: ' + String( message_index ) + ' </b>' +  String(  content   )
    } else {
    response_area.innerHTML =  String(  content   )
    }
  }
  const comment_text = comment;
  const submitBtn = document.getElementById("submitBtn");
  if (submitBtn) {
    if (comment_text === "") {
      button_color(submitBtn, "red");
    } else {
      submitBtn.style.display = "block";
    }
  }
  fix_box();
  document.cookie = "busy=false; max-age=3600; path=/";
}
document.querySelectorAll('span[name="queryrow"]').forEach((row) => {
  var btn =  row.querySelector('button[name="oldquery"]');
  btn.addEventListener("click", handleClick);
});

document.addEventListener("DOMContentLoaded", function () {
  const selectAll = document.getElementById("select-all");
  if (selectAll) {
    selectAll.addEventListener("change", function () {
      const checked = this.checked;
      var btns = document.querySelectorAll(".choice-box");
      btns.forEach((cb) => (cb.checked = checked));
    });
  }

  const myForm = document.getElementById("myForm");
  if (myForm) {
    myForm.addEventListener("input", function () {
      const sendButton = document.getElementById("send-button");
      if (sendButton) {
        button_color(sendButton, "green");
        sendButton.click();
      }
    });
  }
});

function fix_box() {
  let selectedValue = document.querySelector(
    'input[name="option"]:checked'
  )?.value;

  if (selectedValue == 0) {
    document.getElementById("button-box").style.border = "2px dashed red ";
  } else {
    document.getElementById("button-box").style.border = "2px dashed black ";
  }
}

button_color(document.getElementById("send-button"), "red");
button_color(document.getElementById("submitBtn"), "red");

$(document).ready(function () {
  document.getElementsByName("query")[0].addEventListener("input", function () {
    let selectedValue = document.querySelector(
      'input[name="option"]:checked'
    )?.value;
    try {
      fix_box();
    } catch {}
    button_color(document.getElementById("send-button"), "red");
    const response_area = document.getElementById("response").innerHTML;
    // console.log("selectedValue", selectedValue, "len=", response_area.length , response_area);
    var first_word = response_area.trim().split(/\s+/)[0];
    // console.log("FIRST_WORD = ", first_word);
    if (selectedValue == 0 && first_word != 'None') {
      button_color(document.getElementById("submitBtn"), "red");
      if (!first_word.includes("ERROR")) {
        alert(
          "You must read and assess the response before with a new related query."
        );
      } else {
        button_color(document.getElementById("submitBtn"), "green");
      }
    } else {
      button_color(document.getElementById("submitBtn"), "green");
    }
  });

  const textarea = document.getElementById("id_query").innerHTML;
  if (textarea == "") {
    document.getElementById("response-block").style.display = "none";
  }
  $("#myForm").on("submit", function (e) {
    e.preventDefault(); // Prevent full form submission
    document.getElementById("button-box").style.border = "1px dashed black";
    fix_box();

    $.ajax({
      type: "POST",
      url: "/django_ragamuffin/feedback/",
      data: $(this).serialize(),
      headers: {
        "X-CSRFToken": $("input[name=csrfmiddlewaretoken]").val(),
      },
      success: function (response) {
        const mindex = response["index"];
        const mcomment = document.getElementById("comment-" + mindex);
        mcomment.textContent = response["comment"];
        const mchoice = document.getElementById("choice-" + mindex);
        mchoice.textContent = response["choice"];
        button_color(document.getElementById("submitBtn"), "green");
        button_color(document.getElementById("send-button"), "red");
        fix_box();
      },
      error: function (_, __, error) {
        console.error("Error:", error);
      },
    });
  });
});
