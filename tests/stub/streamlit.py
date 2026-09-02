"""Minimal Streamlit stub to exercise render() paths offline."""
import functools, contextlib
LOG=[]
class SS(dict):
    def __getattr__(s,k):
        try: return s[k]
        except KeyError: raise AttributeError(k)
    def __setattr__(s,k,v): s[k]=v
    def setdefault(s,k,v=None): return dict.setdefault(s,k,v)
session_state=SS()
class Col:
    def __enter__(s): return s
    def __exit__(s,*a): return False
    def __getattr__(s,n): return globals().get(n, lambda *a,**k: None)
def columns(spec,**k):
    n=spec if isinstance(spec,int) else len(spec)
    return [Col() for _ in range(n)]
def markdown(t,**k): LOG.append(("md",t))
def write(*a,**k): LOG.append(("w",a))
def selectbox(label,opts,index=0,format_func=str,key=None,**k):
    opts=list(opts); LOG.append(("sel",label,len(opts))); return opts[index] if opts else None
def radio(label,opts,index=0,**k): return list(opts)[index]
def multiselect(label,opts,default=None,**k): return list(default) if default else []
def button(label,**k): LOG.append(("btn",label)); return False
def divider(): pass
def caption(t,**k): LOG.append(("cap",t))
def info(t,**k): LOG.append(("info",t))
def warning(t,**k): LOG.append(("warn",t))
def error(t,**k): LOG.append(("err",t))
def subheader(t,**k): pass
def header(t,**k): pass
def dataframe(*a,**k): pass
def plotly_chart(*a,**k): pass
def metric(*a,**k): pass
def rerun(): raise RuntimeError("RERUN")
def set_page_config(**k): pass
@contextlib.contextmanager
def sidebar_cm():
    yield
class _SB:
    def __enter__(s): return s
    def __exit__(s,*a): return False
sidebar=_SB()
def container(**k): return Col()
def expander(*a,**k): return Col()
def spinner(*a,**k): return Col()
def empty(): return Col()
def cache_data(func=None,**k):
    def deco(f):
        f.clear=lambda: None
        return f
    return deco(func) if callable(func) else deco
cache_resource=cache_data
def number_input(label,*a,value=0,**k):
    return value if value is not None else (a[0] if a else 0)
def json(*a,**k): pass
def code(*a,**k): pass
def table(*a,**k): pass
def image(*a,**k): pass
def download_button(*a,**k): return False
def select_slider(label,options=None,value=None,**k): return value if value is not None else (list(options)[0] if options else None)
def segmented_control(label,options,**k): return list(options)[0] if options else None
def pills(label,options,**k): return None
def link_button(*a,**k): return False
def status(*a,**k): return Col()
def toast(*a,**k): pass
def balloons(): pass
def altair_chart(*a,**k): pass
def line_chart(*a,**k): pass
def bar_chart(*a,**k): pass
def text_input(label,*a,value="",**k): return value
def slider(label,*a,value=None,**k):
    if value is not None: return value
    if len(a)>=3: return a[2]
    if len(a)==2: return a[0]
    return 0
def checkbox(label,value=False,**k): return value
def file_uploader(*a,**k): return None
def tabs(names): return [Col() for _ in names]
def toggle(label,value=False,**k): return value
def date_input(label,value=None,**k): return value
def form(*a,**k): return Col()
def form_submit_button(*a,**k): return False
def progress(*a,**k): return Col()
def success(t,**k): pass
def stop(): raise SystemExit
