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
from django_ragamuffin.models import VectorStore, Assistant
from django.utils.safestring import mark_safe
from django.http import FileResponse
import logging
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




MAX_OLD_QUERIES = 30
def mathfix( txt ):
    txt = re.sub(r"_","UNDERSCORE",txt)
    txt = re.sub(r"\\\(",'$',txt)
    txt = re.sub(r"\\\)",'$',txt)
    txt = re.sub(r"\\\[",'LEFTBRAK',txt)
    txt = re.sub(r"\\\]",'RIGHTBRAK',txt)
    txt = markdown2.markdown( txt )
    txt = re.sub(r"LEFTBRAK",'<p/>$\\;',txt)
    txt = re.sub(r"RIGHTBRAK",'\\;$<p/>',txt)
    txt = re.sub(r"UNDERSCORE",'_',txt)
    txt = markdown2.markdown(txt)
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
    assistant = thread.assistant;
    h = msg.get('hash',get_hash() )
    subdir =  assistant.name.split('.')
    p = os.path.join('/subdomain-data','openai','queries', *subdir,thread.user.username,)
    os.makedirs(p, exist_ok=True )
    fn = f"{p}/{h}.json"
    msgsave = msg
    msgsave.update({'name' : assistant.name,'hash' : h })
    with open(fn, "w") as f:
        json.dump(msgsave,  f , indent=2)

CHOICES = {0 : 'Unread' ,
           1 : 'Incomplete' , 
           2 : 'Wrong', 
           3 : 'Irrelevant',
           4 : "Superficial." ,  
           5 : "Unhelpful", 
           6 : 'Partly Correct', 
           7 : 'Completely Correct'}






def get_assistant( name,user):
    assistants = Assistant.objects.filter(name=name).all();
    logger.info(f"GET_ASSISTANT assistants = {assistants}")
    if not assistants and not user.is_staff :
        return None
    if user.is_staff :
        model = settings.AI_MODELS['staff']
    else :
        model = settings.AI_MODELS['default']
    assistants_ = Assistant.objects.filter(name=name, model=model).all()
    if assistants_ :
        return  assistants_[0]
    if assistants :
        a = assistants[0];
        return a.clone(name,model=model)
    base = '.'.join(name.split('.')[:-1])
    if base == '' :
        return None
    subdir = name.split('.')[-1];
    base_assistant = get_assistant( base ,user );
    if base_assistant :
        assistant = base_assistant.clone( name , model=model)
    else :
        for m in settings.AI_MODELS.values()  :
            assistant = Assistant(name=name,model=m);
            vs = VectorStore(name=name);
            vs.save();
            assistant.save();
            assistant.vector_stores.set([vs.pk])
            assistant.save();
        assistant = Assistant.objects.get(name=name,model=model)
    return assistant 

def thread_to_pdf( thread , prints ):
    messages = thread.messages;
    iprints = [int(i) for i in prints ];
    ps = [(i,x) for i,x in enumerate(messages) if i in iprints ]

    file = open("/tmp/tmp.tex","w");
    file.write(head)
    for (i,p) in ps :
        msg = p;
        q = msg['user'];
        r = msg['assistant']
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
        name = thread.name
        #file.write(f"\\fancyhead[R]{{ \\hspace{{1cm}} \\textbf{{ {name} }} }}\n");
        file.write(f"\\fancyhead[R]{{\\makebox[0pt][l]{{\\hspace{{-4cm}}\\textbf{{ {name} }}}} }} ")
        file.write(boxhead)
        #file.write(f"\n\\textbf{{Assistant: {name} }}\n\\vspace{{8pt}}\n\n")
        file.write(f"\n\\textbf{{Question {i} :}} {q}\n{boxtail}\n\\textbf{{Response:}} {r}\n")
        file.write(f"\n\\vspace{{8pt}}\n") 
        file.write(f"\n\\textbf{{tokens={msg.get('ntokens',0)} dt={time_spent} model={model} choice={choice} {v} }} \\vspace{{12pt}} \n\n " )
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

