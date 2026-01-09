# Python环境搭建

## 下载python

https://www.python.org/downloads/

## 配置pip工具

```
$ python3 -m ensurepip --default-pip
Looking in links: /var/folders/kl/rrg84m511h37lrnsr_9jbg0m0000gn/T/tmplctkxg2u
Requirement already satisfied: setuptools in /Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages (65.5.0)
Requirement already satisfied: pip in /Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages (24.0)
```

## 配置环境变量

open ~/.bash_profile

输入下面内容：

```bash
export PYTHON_HOME=/Library/Frameworks/Python.framework/Versions/3.11
export PATH=$PYTHON_HOME/bin:$PATH
alias python=$PYTHON_HOME/bin/python3.11
alias pip=$PYTHON_HOME/bin/pip3.11
```

让配置生效：

source .bash_profile
