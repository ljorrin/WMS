from fastapi import FastAPI, Response, status

try:
    app1 = FastAPI()
    @app1.delete("/test1", status_code=status.HTTP_204_NO_CONTENT)
    def test1() -> None:
        pass
    print("test1 success")
except Exception as e:
    print("test1 fail:", type(e), e)

try:
    app2 = FastAPI()
    @app2.delete("/test2", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
    def test2() -> None:
        pass
    print("test2 success")
except Exception as e:
    print("test2 fail:", type(e), e)

try:
    app3 = FastAPI()
    @app3.delete("/test3", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
    def test3() -> None:
        pass
    print("test3 success")
except Exception as e:
    print("test3 fail:", type(e), e)

try:
    app4 = FastAPI()
    @app4.delete("/test4", status_code=status.HTTP_204_NO_CONTENT)
    def test4():
        pass
    print("test4 success")
except Exception as e:
    print("test4 fail:", type(e), e)

try:
    app5 = FastAPI()
    @app5.delete("/test5", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
    def test5():
        pass
    print("test5 success")
except Exception as e:
    print("test5 fail:", type(e), e)
