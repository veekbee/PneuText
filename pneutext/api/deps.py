"""Dependencies shared by the routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from pneutext.store.library import Library


def get_library(request: Request) -> Library:
    return request.app.state.library


LibraryDep = Annotated[Library, Depends(get_library)]
