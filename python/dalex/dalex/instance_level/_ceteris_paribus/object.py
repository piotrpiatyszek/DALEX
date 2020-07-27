from warnings import warn

import plotly.express as px

from .checks import *
from .utils import calculate_ceteris_paribus
from .plot import tooltip_text
from ..._explainer.theme import get_default_colors, fig_update_line_plot


class CeterisParibus:
    def __init__(self,
                 variables=None,
                 grid_points=101,
                 variable_splits=None,
                 variable_splits_type='uniform',
                 include_new_observation=True,
                 processes=1):
        """
        Creates Ceteris Paribus object

        :param variables: variables for which the profiles are calculated
        :param grid_points: number of points in a single variable split if calculated automatically
        :param variable_splits: mapping of variables into points the profile will be calculated, if None then calculate with the function `_calculate_variable_splits`
        :param variable_splits_type: way of calculating variable_splits, se "quantiles" (default) for percentiles or "uniform" to get uniform grid of points
        :param processes: integer, number of parallel processes, iterated over variables

        :return None
        """

        processes_ = check_processes(processes)
        variable_splits_type_ = check_variable_splits_type(variable_splits_type)

        self.variables = variables
        self.grid_points = grid_points
        self.variable_splits = variable_splits
        self.variable_splits_type = variable_splits_type_
        self.include_new_observation = include_new_observation
        self.result = None
        self.new_observation = None
        self.processes = processes_

    def fit(self,
            explainer,
            new_observation,
            y=None,
            verbose=True):

        self.variables = check_variables(self.variables, explainer, self.variable_splits)

        check_data(explainer.data, self.variables)

        self.new_observation = check_new_observation(new_observation, explainer)

        self.variable_splits = check_variable_splits(self.variable_splits,
                                                     self.variables,
                                                     self.grid_points,
                                                     explainer.data,
                                                     self.variable_splits_type,
                                                     self.include_new_observation,
                                                     self.new_observation)

        y = check_y(y)

        self.result, self.new_observation = calculate_ceteris_paribus(explainer,
                                                                      self.new_observation,
                                                                      self.variable_splits,
                                                                      y,
                                                                      self.processes,
                                                                      verbose)

    def plot(self,
             objects=None,
             variable_type="numerical",
             variables=None,
             size=2,
             alpha=1,
             color="_label_",
             facet_ncol=2,
             show_observations=True,
             title="Ceteris Paribus Profiles",
             title_x='prediction',
             horizontal_spacing=0.05,
             vertical_spacing=None,
             show=True):
        """Plot the Ceteris Paribus explanation

        Parameters
        -----------
        objects : CeterisParibus object or array_like of CeterisParibus objects
            Additional objects to plot in subplots (default is None).
        variable_type : {'numerical', 'categorical'}
            Plot the profiles for numerical or categorical variables (default is 'numerical').
        variables : str or array_like of str, optional
            Variables for which the profiles will be calculated
            (default is None, which means all of the variables).
        size : float, optional
            Width of lines in px (default is 2).
        alpha : float <0, 1>, optional
            Opacity of lines (default is 1).
        color : str, optional
            Variable name used for grouping (default is '_label_', which groups by models).
        facet_ncol : int, optional
            Number of columns on the plot grid (default is 2).
        show_observations : bool, optional
            Show observation points (default is True).
        title : str, optional
            Title of the plot (default is "Ceteris Paribus Profiles").
        title_x : str, optional
            Title of the x axis (default is "prediction").
        horizontal_spacing : float <0, 1>, optional
            Ratio of horizontal space between the plots (default is 0.05).
        vertical_spacing : float <0, 1>, optional
            Ratio of vertical space between the plots (default is 0.3/number of rows).
        show : bool, optional
            True shows the plot; False returns the plotly Figure object that can be
            edited or saved using the `write_image()` method (default is True).

        Returns
        -----------
        None or plotly.graph_objects.Figure
            Return figure that can be edited or saved. See `show` parameter.
        """

        # TODO: numerical+categorical in one plot https://github.com/plotly/plotly.py/issues/2647

        if variable_type not in ("numerical", "categorical"):
            raise TypeError("variable_type should be 'numerical' or 'categorical'")
        if isinstance(variables, str):
            variables = (variables,)

        # are there any other objects to plot?
        if objects is None:
            _result_df = self.result.copy()
            _include = self.include_new_observation
        elif isinstance(objects, self.__class__):  # allow for objects to be a single element
            _result_df = pd.concat([self.result.copy(), objects.result.copy()])
            _include = np.all([self.include_new_observation, objects.include_new_observation])
        else:  # objects as tuple or array
            _result_df = self.result.copy()
            _include = [self.include_new_observation]
            for ob in objects:
                if not isinstance(ob, self.__class__):
                    raise TypeError("Some explanations aren't of CeterisParibus class")
                _result_df = pd.concat([_result_df, ob.result.copy()])
                _include += [ob.include_new_observation]
            _include = np.all(_include)

        if _include is False and show_observations:
                warnings.warn("show_observations will be set to False,"
                              "because the include_new_observation attribute is False"
                              "See `include_new_observation` parameter in `predict_profile`.")
                show_observations = False

        # variables to use
        all_variables = list(_result_df['_vname_'].dropna().unique())

        if variables is not None:
            all_variables = np.intersect1d(all_variables, variables).tolist()
            if len(all_variables) == 0:
                raise TypeError("variables do not overlap with " + ''.join(variables))

        # names of numeric variables
        numeric_variables = _result_df[all_variables].select_dtypes(include=np.number).columns.tolist()

        if variable_type == "numerical":
            variable_names = numeric_variables

            if len(variable_names) == 0:
                # change to categorical
                variable_type = "categorical"
                # send message
                warn("'variable_type' changed to 'categorical' due to lack of numerical variables.")
                # take all
                variable_names = all_variables
            elif variables is not None and len(variable_names) != len(variables):
                raise TypeError("There are no numerical variables")
        else:
            variable_names = np.setdiff1d(all_variables, numeric_variables).tolist()

            # there are variables selected
            if variables is not None:
                # take all
                variable_names = all_variables
            elif len(variable_names) == 0:
                # there were no variables selected and there are no categorical variables
                raise TypeError("There are no non-numerical variables.")

        # prepare profiles data
        _result_df = _result_df.loc[_result_df['_vname_'].isin(variable_names), ].reset_index(drop=True)

        # create _x_
        for variable in variable_names:
            where_variable = _result_df['_vname_'] == variable
            _result_df.loc[where_variable, '_x_'] = _result_df.loc[where_variable, variable]

        # change x column to proper character values
        if variable_type == 'categorical':
            _result_df.loc[:, '_x_'] = _result_df.apply(lambda row: str(row[row['_vname_']]), axis=1)

        n = len(variable_names)
        facet_nrow = int(np.ceil(n / facet_ncol))
        if vertical_spacing is None:
            vertical_spacing = 0.3 / facet_nrow

        plot_height = 78 + 71 + facet_nrow * (280 + 60)

        m = len(_result_df[color].dropna().unique())

        _result_df[color] = _result_df[color].astype(object)  # prevent error when using pd.StringDtype
        _result_df = _result_df.assign(_text_=_result_df.apply(lambda obs: tooltip_text(obs), axis=1))

        if variable_type == "numerical":

            fig = px.line(_result_df,
                          x="_x_", y="_yhat_", color=color, facet_col="_vname_", line_group='_ids_',
                          category_orders={"_vname_": list(variable_names)},
                          labels={'_yhat_': 'prediction', '_label_': 'label', '_ids_': 'id'},  # , color: 'group'},
                          # hover_data={'_text_': True, '_yhat_': ':.3f', '_vname_': False, '_x_': False, color: False},
                          custom_data=['_text_'],
                          facet_col_wrap=facet_ncol,
                          facet_row_spacing=vertical_spacing,
                          facet_col_spacing=horizontal_spacing,
                          template="none",
                          color_discrete_sequence=get_default_colors(m, 'line')) \
                    .update_traces(dict(line_width=size, opacity=alpha,
                                        hovertemplate="%{customdata[0]}<extra></extra>")) \
                    .update_xaxes({'matches': None, 'showticklabels': True,
                                   'type': 'linear', 'gridwidth': 2, 'zeroline': False, 'automargin': True,
                                   'ticks': "outside", 'tickcolor': 'white', 'ticklen': 3, 'fixedrange': True}) \
                    .update_yaxes({'type': 'linear', 'gridwidth': 2, 'zeroline': False, 'automargin': True,
                                   'ticks': 'outside', 'tickcolor': 'white', 'ticklen': 3, 'fixedrange': True})

            if show_observations:
                _points_df = _result_df.loc[_result_df['_original_'] == _result_df['_x_'], :].copy()

                fig_points = px.scatter(_points_df,
                                        x='_original_', y='_yhat_', facet_col='_vname_',
                                        category_orders={"_vname_": list(variable_names)},
                                        labels={'_yhat_': 'prediction', '_label_': 'label', '_ids_': 'id'},
                                        custom_data=['_text_'],
                                        facet_col_wrap=facet_ncol,
                                        facet_row_spacing=vertical_spacing,
                                        facet_col_spacing=horizontal_spacing,
                                        color_discrete_sequence=["#371ea3"]) \
                               .update_traces(dict(marker_size=5*size, opacity=alpha),
                                              hovertemplate="%{customdata[0]}<extra></extra>")

                for _, value in enumerate(fig_points.data):
                    fig.add_trace(value)

        else:
            if len(_result_df['_ids_'].unique()) > 1:  # https://github.com/plotly/plotly.py/issues/2657
                raise TypeError("Please pick one observation per label.")

            fig = px.bar(_result_df,
                         x="_x_", y="_yhat_", color="_label_", facet_col="_vname_",
                         category_orders={"_vname_": list(variable_names)},
                         labels={'_yhat_': 'prediction', '_label_': 'label', '_ids_': 'id'},  # , color: 'group'},
                         # hover_data={'_yhat_': ':.3f', '_ids_': True, '_vname_': False, color: False},
                         custom_data=['_text_'],
                         facet_col_wrap=facet_ncol,
                         facet_row_spacing=vertical_spacing,
                         facet_col_spacing=horizontal_spacing,
                         template="none",
                         color_discrete_sequence=get_default_colors(m, 'line'),  # bar was forgotten
                         barmode='group')  \
                    .update_traces(dict(opacity=alpha),
                                   hovertemplate="%{customdata[0]}<extra></extra>") \
                    .update_xaxes({'matches': None, 'showticklabels': True,
                                   'type': 'category', 'gridwidth': 2, 'autorange': 'reversed', 'automargin': True,
                                   'ticks': "outside", 'tickcolor': 'white', 'ticklen': 10, 'fixedrange': True}) \
                    .update_yaxes({'type': 'linear', 'gridwidth': 2, 'zeroline': False, 'automargin': True,
                                   'ticks': 'outside', 'tickcolor': 'white', 'ticklen': 3, 'fixedrange': True})

        fig = fig_update_line_plot(fig, title, title_x, plot_height, 'closest')

        fig.update_layout(
            hoverlabel=dict(bgcolor='rgba(0,0,0,0.8)')
        )

        if show:
            fig.show(config={'displaylogo': False, 'staticPlot': False,
                             'toImageButtonOptions': {'height': None, 'width': None, },
                             'modeBarButtonsToRemove': ['sendDataToCloud', 'lasso2d', 'autoScale2d', 'select2d',
                                                        'zoom2d', 'pan2d',
                                                        'zoomIn2d', 'zoomOut2d', 'resetScale2d', 'toggleSpikelines',
                                                        'hoverCompareCartesian',
                                                        'hoverClosestCartesian']})
        else:
            return fig
