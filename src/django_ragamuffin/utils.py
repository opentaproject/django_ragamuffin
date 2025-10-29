import json
import re
import pypandoc
import markdown2
from pathlib import Path
import subprocess
from django.conf import settings
import os
import string
import random
from django_ragamuffin.models import VectorStore, Assistant, Mode, ModeChoice, Thread, CHOICES
from django.utils.safestring import mark_safe
from django.http import FileResponse
import logging
from typing import Tuple, Dict
logger = logging.getLogger(__name__)

head = " \
\\documentclass{article}\n\
\\usepackage{amsmath} \n\
\\usepackage[a4paper, right=2.5cm, left=2.0cm, top=1.5cm]{geometry} \n\
\\usepackage{graphicx} \n\
\\usepackage{mdframed} \n\
\\usepackage{amsmath} \n\
\\usepackage{fancyhdr,hyperref,mathrsfs}\n\
\\pagestyle{fancy}\n\
\\fancyhf{} \n\
\\providecommand{\\tightlist}{\n\
  \\setlength{\\itemsep}{0pt}\\setlength{\\parskip}{0pt}}\n\
\\begin{document} \n\
\\setlength{\parindent}{0pt} \n\
\\setlength{\parsep}{2pt} \n\
\\setlength{\\fboxsep}{5pt}   \n\
\\setlength{\\fboxrule}{0.5pt}"
tail = "\n\\end{document}"
boxhead = "\n\n\\fbox{\n\
\\parbox{\\dimexpr\\linewidth-2\\fboxsep-2\\fboxrule\\relax}{\n"
boxtail = "\n}}\n\\vspace{12pt}\n"

boxhead = "\n\n\\hspace*{-20pt}\\fbox{\n\
\\parbox{\\dimexpr\\linewidth-2\\fboxsep-2\\fboxrule\\relax}{\n"


_MATH_RE = re.compile(
    r'(?<!\\)\$\$(.+?)(?<!\\)\$\$'      # block-style, $$...$$
    r'|(?<!\\)\$(.+?)(?<!\\)\$',        # inline, $...$
    flags=re.DOTALL
)
_MATH_RE = re.compile(
    r'(?<!\\)(?:\$\$(.+?)(?<!\\)\$\$|\$(.+?)(?<!\\)\$)',
    flags=re.DOTALL
)

def tokenize_math_dollars(text: str) -> Tuple[str, Dict[str, dict]]:
    """
    Replace every unescaped $...$ or $$...$$ span with a unique token.
    Returns (new_text, mapping) where mapping[token] = {"content": <inside>,
    "delim": "$" or "$$"}.

    - Keeps unmatched/escaped \$ or \$\$ intact.
    - Uses rare bracket/label tokens to minimize collisions.
    """
    counter = 0
    mapping: Dict[str, dict] = {}

    def _repl(m: re.Match) -> str:
        nonlocal counter
        # m.group(1) corresponds to $$...$$, m.group(2) to $...$
        if m.group(1) is not None:
            inside = m.group(1)
            delimleft = " \\[ "
            delimright = " \\] "
        else:
            inside = m.group(2)
            delimleft = "$"
            delimright = "$"


        token = f"⟦MATH:{counter}⟧"
        insideorig = inside
        inside = re.sub(r"\\-"," - ",  inside )
        inside = re.sub(r"\\\\,","  ",  inside )
        inside = inside.replace(r"\\\\\!", "")
        #inside = re.sub(r"\\n",r" ",inside)
        #inside = inside.replace(r"boldsymbol","bold")
        for p in ['boxed' ,'aligned' ] :
            if p in  insideorig :
                delimleft = '$$';
                delimright = '$$';
        mapping[token] = {"content": inside, "delimleft": delimleft, "delimright" : delimright}
        counter += 1
        return token
    text = text.replace(r'\\[',r'$$ ')
    text = text.replace(r'\\]',r' $$')

    new_text = _MATH_RE.sub(_repl, text)
    return new_text, mapping


def restore_math_tokens(text: str, mapping: Dict[str, dict]) -> str:
    """
    Replace tokens back with their original math, re-wrapping in the
    correct delimiter length ($ or $$).
    """
    # Sort by descending token length just in case (defensive)
    for token in sorted(mapping.keys(), key=len, reverse=True):
        item = mapping[token]
        wrapped = f"{item['delimleft']} {item['content']} {item['delimright']}"
        text = text.replace(token, wrapped)
    return text

def strip_openai_citations(text: str) -> str:
    """
    Remove all OpenAI citation markers and artifacts (, 【...†...】, etc.)
    from a model response.
    """
    if not text:
        return ""

    # Remove full invisible filecite markers ()
    text = re.sub(r'', '', text)

    # Remove any leftover fragments like ''
    text = re.sub(r'[]', '', text)

    # Remove reference markers like   or  
    text = re.sub(r'【[^】]*†[^】]*】', '', text)

    # Also catch any orphan 【...】 pairs
    text = re.sub(r'【[^】]*】', '', text)

    # Clean up double spaces and stray brackets
    text = re.sub(r'\s{2,}', ' ', text)
    #text = re.sub(r'\s*\]\s*', ' ', text)

    return text.strip()


MAX_OLD_QUERIES = 30
def mathfix( txt ):
    #print(f"MATHFIX_IN {txt}")
    #txt = strip_openai_citations(txt)
    txt = re.sub(r'\[[0-9]+pt\]','',txt)
    txt = re.sub(r'\$[, ]+\$[, ]+\$',r'$$',txt);
    txt = re.sub(r'\$[, ]+\$','$$',txt)
    #txt = re.sub(r"\\\(",'$',txt)
    #txt = re.sub(r"\\\)",'$',txt)
    #txt = re.sub(r"\$",' $ ',txt )
    #txt = re.sub(r"\\\[",'LEFTBRAK',txt)
    #txt = re.sub(r"\\\]",'RIGHTBRAK',txt)
    #txt = re.sub(r"LEFTBRAK",'<p/>$\\;',txt)
    #txt = re.sub(r"RIGHTBRAK",'\\;$<p/>',txt)
    #txt = re.sub(r'([A-Za-z_]{2,})!', r'\1',txt)
    #txt = re.sub(r'(?<!\\)_', r'\\_', txt)
    #txt = re.sub(r'(_\w)!', r'\1',txt)   
    #txt = re.sub(r'(\w\')!', r'\1',txt)  # SHOULD NOT BE HERE
    #txt = re.sub(r'(\w\')\!', r'\1',txt) # SHOULD NOT BE HERE
    #txt = re.sub(r'(\w\')\\!', r'\1',txt)
    #txt = re.sub(r"operatorname","bold",txt )
    txt = re.sub(r"texttt","mathtt",txt )
    #txt = re.sub(r"\$\$(.*?)\$\$", r"<p/><p/>$\1$<p/><p/>", txt, flags=re.S)
    txt = re.sub(r"\\dots", r"\\ldots", txt )
    #txt = re.sub(r'fileciteturn0file[0-9]+\.', '', txt )
    #print(f"TXT_BEFORE_MARKDOWN\n{txt}")
    #txt = re.sub(r"\\\\",r"\\",txt)
    txt = re.sub(r'\\\\(?=[A-Za-z])', r'\\', txt )
    #txt = re.sub(r"\\ ",r"\\\\",txt)
    #print(f"TXT2_BEFORE_MARKDOWN\n{txt}")
    #txt = re.sub(r"\&",r' AMPERSAND ',txt)
    txt,mapping = tokenize_math_dollars(txt)
    #print(f"MAPPING = {mapping}")
    txt = markdown2.markdown(txt )
    #print(f"TXT3_AFTER_MARKDOWN\n{txt}")
    #txt = re.sub(r" AMPERSAND ",r'&',txt)
    #txt = re.sub(r" DOUBLEBACKSLASH ",r'\\\\',txt)
    #txt = re.sub(r"\\-",'\\ - ',txt)
    txt = restore_math_tokens(txt, mapping)
    txt = re.sub(r"operatorname","mathrm",txt )
    #txt = re.sub(r"\$\$",'$',txt)
    #print(f"TXT MATTHFIX_OUT\n{txt}")
    txt = re.sub(r"[\ue000-\uf8ff]\S*", "", txt )
    #txt = mark_safe(txt)
    

    return txt


def tex_to_pdf(tex_code , output_dir="output", jobname="document"):
    # Create a temp directory for compilation
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    tex_file = output_path / f"{jobname}.tex"
    with tex_file.open("w") as f:
        f.write(tex_code )
    
    subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-output-directory", output_dir, tex_file.name],
        cwd=output_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    
    return output_path / f"{jobname}.pdf"


def get_hash() :
 characters = string.ascii_letters + string.digits  # a-zA-Z0-9
 h = ''.join(random.choices(characters, k=8))
 return h


def doarchive( thread, msg ):
    assistant = thread.assistant
    if not assistant :
        assistant , _ = Assistant.objects.get_or_create(name=thread.name)
    h = msg.get('hash',get_hash() )
    subdir =  assistant.name.split('.')
    p = os.path.join('/subdomain-data','openai','queries', *subdir,thread.user.username,)
    os.makedirs(p, exist_ok=True )
    fn = f"{p}/{h}.json"
    msgsave = msg
    msgsave.update({'name' : assistant.name,'hash' : h })
    with open(fn, "w") as f:
        json.dump(msgsave,  f , indent=2)


def print_messages( thread ):
    #print(f"PRINT MESSAGES {thread}")
    ms = thread.thread_messages.all()
    #print(f"\n")
    clear = thread.clear
    try :
        for m in ms :
            previous_response_id = m.get('previous_response_id','none1')
            response_id = m.get('response_id','none2')
            user = m.get('user','nouser')
            response = m.get('assistant','noreponse')[0:15]
            #print(f"clear={clear} previous={previous_response_id} id={response_id} query={user} response={response}")
    except :
            print(f"ms = {ms}")
    print("\n")



def print_my_stack():
    import sys,os,traceback
    stdlib = os.path.dirname(os.__file__)
    sitepkgs = next(p for p in sys.path if "site-packages" in p)
    stack = traceback.extract_stack()
    for frame in stack:
        f = os.path.abspath(frame.filename)
        if not f.startswith(stdlib) and not f.startswith(sitepkgs):
            print(f"{frame.filename}:{frame.lineno} in {frame.name}")




def get_assistant( name , quser ):
    #print(f"GET_ASSISTANT NAM={name} QUSER={quser}")
    assistants = Assistant.objects.filter(name=name).all();
    #print(f"GET_ASSISTANT assistants = {assistants}")
    model = settings.AI_MODEL
    if not assistants and not quser.is_staff :
        return None
    if assistants :
        return  assistants[0]
    base = '.'.join(name.split('.')[:-1])
    #print(f"BASE = {base}")
    if base == '' :
        return None
    subdir = name.split('.')[-1];
    base_assistant = get_assistant( base,quser);
    #print("BASE_ASSISTANT = ", base_assistant)
    if base_assistant :
        assistant = base_assistant.clone_stub( name )
    else :
        assistant = Assistant(name=name);
        #vs = VectorStore(name=name);
        #vs.save();
        assistant.save();
        #assistant.vector_stores.set([vs.pk])
        #assistant.save();
        #assistant = Assistant.objects.get(name=name,model=model)
    return assistant 

def messages_to_pdf( assistant , messages, prints ):
    iprints = [int(i) for i in prints ];
    pks = [ m['id'] for m in messages ]
    ps = [(i,x) for i,x in enumerate(messages) if ( x['id']  in iprints ) ]
    mode = assistant.mode_choice
    vv = 'Query'
    if mode == None :
        vv = ''
    else :
        match f"{mode}":
            case 'Examiner' :
                vv = 'Attempt'
            case 'Assistant' :
                vv = 'Query'
            case _:
                vv = 'Query'

    file = open("/tmp/tmp.tex","w");
    file.write(head)
    for (i,p) in ps :
        msg = p;
        q = msg['query'];
        r = msg['response']
        r =  mark_safe( mathfix(r)  );
        r = pypandoc.convert_text( r ,'latex', format='html+raw_tex', extra_args=["--wrap=preserve"]  )
        def pandoc_fix(r) :
            r = re.sub(r'\\\$','$',r);
            r = re.sub(r'\\\(','$',r);
            r = re.sub(r'\\\)','R',r);
            r = re.sub(r'\\_','_',r);
            r = re.sub(r'textbackslash *','',r)
            r = re.sub(r'\\textquotesingle',"\'",r)
            r = re.sub(r'\\{','{',r);
            r = re.sub(r'\\}','}',r);
            r = re.sub(r'\\\^','^',r);
            r = re.sub(r'\\textgreater','>',r)
            r = re.sub(r'textasciitilde','',r)
            r = re.sub(r'{}','',r)
            r = re.sub(r'{\[}','[',r);
            r = re.sub(r'{\]}',']',r);
            r = re.sub(r'\\;\$','\\]',r)
            r = re.sub(r'\$\\;','\\[',r)
            r = re.sub(r'section{','section*{\\\\textbullet \\\\hspace{5px} ',r)
            #r = break_after_all_equals( r , max_length=10)
            return r
        r = pandoc_fix(r)
        choice = msg.get('choice',0)
        v = CHOICES[choice]
        time_spent = msg.get('time_spent',0);
        model = msg.get('model','None')
        name = assistant.name
        #file.write(f"\\fancyhead[R]{{ \\hspace{{1cm}} \\textbf{{ {name} }} }}\n");
        file.write(f"\\fancyhead[R]{{\\makebox[0pt][l]{{\\hspace{{-4cm}}\\textbf{{ {name} }}}} }} ")
        file.write(boxhead)
        #file.write(f"\n\\textbf{{Assistant: {name} }}\n\\vspace{{8pt}}\n\n")
        file.write(f"\n\\textbf{{{vv} {i} :}} {q}\n{boxtail}\n\\textbf{{Response:}} {r}\n")
        file.write(f"\n\\vspace{{8pt}}\n") 
        file.write(f"\n\\textbf{{tokens={msg.get('ntokens',0)} dt={time_spent} model={model} {choice}-{v} }} \\vspace{{12pt}} \n\n " )
    file.write(tail)
    file.close();
    try :
        file  = open("/tmp/tmp.tex","rb")
        s = file.read();
        s = s.decode('utf-8')
        pdf = tex_to_pdf(s,"/tmp/")
        pdf_path = "/tmp/document.pdf"
        return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
    except  Exception as err :
        tex_path = "/tmp/tmp.tex"
        return FileResponse(open(tex_path, 'rb'), content_type='application/tex')

