        document.getElementById('submitBtn').addEventListener('click', function () {
            document.cookie = "busy=true; max-age=3600; path=/";
            let count = 0;
            const intervalId = setInterval(() => {
                const busy = getCookie('busy');
                count = count + 1 ;
                if ( count > 80 ){ var patience = ' be patient! It has \'only\' been ' + ( Math.floor( count / 5  ) ).toString() + ' s'  }
                else if ( count > 40 ){ var patience = ' be patient! Give it up to a 2 minutes!' }
                else if( count > 20 ){ var patience = ' be patient!' }
                else { var patience = '' }
                var btn = document.getElementById('submitBtn')
                if ( busy == 'true' ){
                    btn.type = 'button'
                    btn.textContent = 'Wait ... ' + patience
                    btn.style.backgroundColor = "darkorange";
                    btn.style.color = "white"; // optional: for better contrast


                } else {
                    btn.type = 'submit';
                    btn.textContent = 'Submit '
                } }, 200);
            setTimeout(() => {
                clearInterval(intervalId);
                //console.log("Interval stopped");
            }, 120000);
        });

        function button_color( btn , color ) {
            if( color == 'green' ){
                document.getElementById("submitBtn").disabled = false ;
            } else {
                document.getElementById("submitBtn").disabled = true ;
            }

            btn.style.backgroundColor = color;
            btn.style.color = "white"; // optional: for better contrast
            return btn
        }



        function handleClick(event) {
            event.preventDefault() ;
            document.getElementById("response-block").style.display = "block";
            var txt = event.target.value;
            const textarea = document.getElementById('id_query');
            textarea.value = txt
            var innerDiv = event.target.querySelector(".innerDiv");
            var content = innerDiv.innerHTML;
            var innerComment = event.target.querySelector(".innerComment");
            var comment = innerComment.innerHTML;
            const comment_area = document.getElementById('comment');
            comment_area.value = comment


            var innerChoice = event.target.querySelector(".innerChoice");
            var choice = String( innerChoice.innerHTML )
            document.querySelectorAll('input[name="option"]').forEach(function(radio) { radio.checked = false; });
            document.querySelector(`input[name="option"][value="${choice}"]`).checked = true;



            const response_area = document.getElementById('response');
            response_area.innerHTML = content
            const message_index = event.target.querySelector('.mindex').innerHTML
            const mindexarea = document.getElementById('newmessage_index');
            const comment_text = comment;
            if( comment_text == '' ){
                button_color(  document.getElementById("submitBtn") ,'red' )
            } else {
                document.getElementById("submitBtn").style.display = "block";
            }
            mindexarea.value = message_index
	    let selectedValue = document.querySelector('input[name="option"]:checked')?.value;
	    //console.log("SELECTED_VALUE = ", selectedValue)
	    fix_box();
            document.cookie = "busy=false ; max-age=3600; path=/";

        }
        document.querySelectorAll('button[name="oldquery"]').forEach(btn => {
            btn.addEventListener('click', handleClick);
        });


        function getCookie(name) {
            const cookieString = document.cookie;
            const cookies = cookieString.split(';');
            for (let cookie of cookies) {
                cookie = cookie.trim();
                if (cookie.startsWith(name + '=')) {
                    return cookie.substring(name.length + 1);
                }
            }
            return null;
        }

        document.getElementById('select-all').addEventListener('change', function () {
            const checked = this.checked;
            var btns = document.querySelectorAll('.choice-box');
            btns.forEach(cb => cb.checked =  checked);
        })

        document.getElementById('myForm').addEventListener('input', function () {
            button_color( document.getElementById("send-button"), 'green' );
	    document.getElementById("send-button").click();
        })

	function fix_box( ) {
	    let selectedValue = document.querySelector('input[name="option"]:checked')?.value;
	    
	    if ( selectedValue == 0 ){
		document.getElementById('button-box').style.border = '2px dashed red ';
		} else {
		document.getElementById('button-box').style.border = '2px dashed black ';

		} 

        }



        button_color( document.getElementById("send-button"), "red");
        button_color( document.getElementById("submitBtn"), "red");

        $(document).ready(function() {
            document.getElementsByName("query")[0].addEventListener("input", function() {
                let selectedValue = document.querySelector('input[name="option"]:checked')?.value;
		    try { 
		fix_box();
		    } catch { }
                button_color( document.getElementById("send-button"), "red");
                const response_area = document.getElementById('response').innerHTML;
		//console.log("selectedValue= ", selectedValue )
		    if ( selectedValue == 0   &&  response_area.length > 20 ){
                    button_color( document.getElementById("submitBtn"), "red");
                    alert("You must read and assess the response before with a new related query.")
                } else {
                    button_color( document.getElementById("submitBtn"), "green");
                };
            });

            const textarea = document.getElementById('id_query').innerHTML;
            try {
                const comment_area = document.getElementById('comment_area').innerHTML;
            } catch { comment_area = ''
            }
            if ( comment_area == '' && textarea != '' ){
                button_color( document.getElementById("submitBtn"), "red")
            }
            if ( textarea == '' ){
                document.getElementById("response-block").style.display = "none";
            }
            $('#myForm').on('submit', function(e) {
                e.preventDefault();  // Prevent full form submission
		document.getElementById('button-box').style.border = '1px dashed black';
		fix_box();
                $.ajax({
                    type: 'POST',
                    url: "{% url  'query' subpath='/feedback'   %}",
                    data: $(this).serialize(),
                    headers: {
                        'X-CSRFToken': $('input[name=csrfmiddlewaretoken]').val()
                    },
                    success: function(response) {
                        //console.log('Success1:', response);
                        const mindex = response['index']
                        const choice = response['choice'];
                        try {
                          const mcomment = document.getElementById('comment-' + mindex );
                          mcomment.textContent = response['comment'];
                        } catch { } 
                        const mchoice = document.getElementById('choice-' + mindex );
                        try {
                          mchoice.textContent = response['choice'];
                        } catch {}
                        let btn = button_color( document.getElementById("submitBtn"), "green")
                        button_color( document.getElementById("send-button"), 'red' )
			//console.log("SUCCESS2")
			let selectedValue = document.querySelector('input[name="option"]:checked')?.value;
			//console.log("SELECTED2 = ", selectedValue )
			fix_box();
                    	},
                    error: function(xhr, status, error) {
                        console.error('Error:', error);
                    }
                });
            });
        });

