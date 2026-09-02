class _F:
    def __init__(self,*a,**k):
        self.data=[]
        if a and a[0] is not None: self.data.append(a[0])
        if k.get("data"): self.data.extend(k["data"] if isinstance(k["data"],list) else [k["data"]])
    def update_layout(self,*a,**k): return self
    def add_trace(self,t=None,*a,**k): self.data.append(t); return self
    def add_vline(self,*a,**k): return self
    def add_hline(self,*a,**k): return self
    def update_xaxes(self,*a,**k): return self
    def update_yaxes(self,*a,**k): return self
    def add_annotation(self,*a,**k): return self
Figure=_F
def Bar(*a,**k): return {"type":"bar"}
def Scatter(*a,**k): return {"type":"scatter"}
def Pie(*a,**k): return {}
def Histogram(*a,**k): return {}
