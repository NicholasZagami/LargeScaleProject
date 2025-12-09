from prefect import flow


@flow
def my_flow():
    print("Hello, Prefect!")


if __name__ == "__main__":
    my_flow.serve(name="my-first-deployment", cron="* * * * *")